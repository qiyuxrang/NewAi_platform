import { randomUUID } from "node:crypto";
import { Router } from "express";
import type { BridgeGatewayClient } from "../gateway-client.js";
import type { BridgeConfig } from "../config.js";
import { asyncHandler, toOpenclawSessionKey } from "../utils.js";

interface ChildSession {
  key: string;
  spawnedBy?: string;
  label?: string;
  displayName?: string;
  status?: string;
  startedAt?: number;
  endedAt?: number;
  model?: string;
  modelProvider?: string;
  lastMessagePreview?: string;
}

type GatewayClient = Pick<BridgeGatewayClient, "request">;
type ControlAction = "steer" | "kill" | "send";

function sessionKey(value: unknown): string | null {
  // Keys are inserted as one native command token; reject whitespace/control characters.
  if (typeof value !== "string" || !value || value.length > 512 || /[\s\x00-\x1f\x7f]/u.test(value)) {
    return null;
  }
  return toOpenclawSessionKey(value);
}

async function listChildren(client: GatewayClient, parent: string): Promise<ChildSession[]> {
  const result = await client.request<{ sessions: ChildSession[] }>("sessions.list", {
    spawnedBy: parent,
    includeLastMessage: true,
  });
  if (!Array.isArray(result.sessions)) {
    throw new Error("Gateway did not return a child session list");
  }
  // Do not trust filtering alone: only expose children with explicit current ownership.
  return result.sessions.filter((child) => child.spawnedBy === parent && sessionKey(child.key));
}

/** Separate paths avoid the existing /sessions/:key(*) route. Mount under /api. */
export function subagentsRoutes(client: GatewayClient, config: Pick<BridgeConfig, "gatewayPort">): Router {
  const router = Router();

  router.get("/subagents", asyncHandler(async (req, res) => {
    const parent = sessionKey(req.query.parent);
    if (!parent) {
      res.status(400).json({ error: "A valid parent session key is required" });
      return;
    }
    const children = await listChildren(client, parent);
    res.json({ parent, children: children.map((child) => ({
      key: child.key,
      spawnedBy: child.spawnedBy,
      label: child.label ?? child.displayName ?? null,
      status: child.status ?? null,
      startedAt: child.startedAt ?? null,
      endedAt: child.endedAt ?? null,
      model: child.model ?? null,
      modelProvider: child.modelProvider ?? null,
      lastMessagePreview: child.lastMessagePreview ?? null,
    })) });
  }));

  router.post("/subagents/:childKey/control", asyncHandler(async (req, res) => {
    const parent = sessionKey(req.body?.parent);
    const childKey = sessionKey(req.params.childKey);
    const action: unknown = req.body?.action;
    const message: unknown = req.body?.message;
    if (!parent || !childKey || !childKey.includes(":")) {
      res.status(400).json({ error: "Valid parent and full child session keys are required" });
      return;
    }
    if (action !== "steer" && action !== "kill" && action !== "send") {
      res.status(400).json({ error: "Supported actions: steer, kill, send" });
      return;
    }
    if (action !== "kill" && (typeof message !== "string" || !message.trim() || message.length > 32_000 || /\x00/u.test(message))) {
      res.status(400).json({ error: "A nonempty message of at most 32000 characters is required" });
      return;
    }
    const children = await listChildren(client, parent);
    if (!children.some((child) => child.key === childKey && child.spawnedBy === parent)) {
      res.status(403).json({ error: "Child session does not currently belong to this parent" });
      return;
    }

    if (action === "kill") {
      // The native HTTP endpoint stops the child directly, outside parent chat dispatch.
      let response;
      try {
        response = await fetch(`http://127.0.0.1:${config.gatewayPort}/sessions/${encodeURIComponent(childKey)}/kill`, {
          method: "POST",
          headers: { "x-openclaw-requester-session-key": parent },
          redirect: "error",
          signal: AbortSignal.timeout(30_000),
        });
      } catch {
        res.status(503).json({ submitted: false, killed: false, error: "Native child stop is unavailable" });
        return;
      }
      if (response.status !== 200) {
        res.status(response.status >= 400 ? response.status : 502).json({ submitted: false, killed: false, error: "Native child stop failed" });
        return;
      }
      const receipt: unknown = await response.json().catch(() => null);
      if (!receipt || typeof receipt !== "object" || !("ok" in receipt) || receipt.ok !== true || !("killed" in receipt) || typeof receipt.killed !== "boolean") {
        res.status(502).json({ submitted: false, killed: false, error: "Native child stop returned an invalid receipt" });
        return;
      }
      if (!receipt.killed) {
        res.status(409).json({ submitted: false, killed: false, error: "Child is already finished or could not be stopped; refresh its status" });
        return;
      }
      const current = (await listChildren(client, parent)).find((child) => child.key === childKey);
      if (current?.status !== "killed") {
        res.status(409).json({ submitted: true, killed: true, verified: false, error: "Native stop accepted but current child status could not be verified; refresh its status" });
        return;
      }
      res.json({ submitted: true, killed: true, verified: true, status: "killed", runId: null });
      return;
    }

    // Native resolver matches full colon-containing childSessionKey exactly.
    // Native control rechecks current controller ownership and run lifecycle.
    const command = `/subagents ${action as ControlAction} ${childKey} ${(message as string).trim()}`;
    const result = await client.request<{ runId?: string }>("chat.send", {
      sessionKey: parent,
      message: command,
      deliver: false,
      idempotencyKey: randomUUID(),
    });
    // chat.send acknowledges dispatch, not successful child completion/control.
    res.status(202).json({ submitted: true, runId: result.runId ?? null });
  }));

  return router;
}
