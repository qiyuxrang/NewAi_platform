import { Router } from "express";
import { listAgentIds, resolveAgentSkillsFilter, resolveAgentWorkspaceDir } from "../../src/agents/agent-scope.js";
import { listChatCommandsForConfig, type ChatCommandDefinition } from "../../src/auto-reply/commands-registry.js";
import type { CommandArgDefinition, CommandCategory, CommandScope } from "../../src/auto-reply/commands-registry.types.js";
import { listSkillCommandsForWorkspace } from "../../src/auto-reply/skill-commands.js";
import { loadConfig } from "../../src/config/config.js";
import { normalizeAgentId } from "../../src/routing/session-key.js";
import type { BridgeConfig } from "../config.js";
import { asyncHandler } from "../utils.js";

interface CommandInfo {
  name: string;
  description: string;
  argument_hint: string | null;
  aliases: string[];
  category: CommandCategory | "skills" | "other";
  scope: CommandScope;
  source: "builtin" | "skill";
  skill_name: string | null;
}

function formatArgHint(args?: CommandArgDefinition[]): string | null {
  if (!args || args.length === 0) {
    return null;
  }
  const parts = args.map((arg) => {
    const base = arg.captureRemaining ? `${arg.name}...` : arg.name;
    return arg.required ? `<${base}>` : `[${base}]`;
  });
  return parts.join(" ");
}

function toCommandInfo(command: ChatCommandDefinition): CommandInfo | null {
  const aliases = command.textAliases
    .map((alias) => alias.trim())
    .filter((alias) => alias.startsWith("/"));
  if (aliases.length === 0) {
    return null;
  }

  const primaryAlias = aliases[0]!;
  const source = command.key.startsWith("skill:") ? "skill" : "builtin";
  const skillName = source === "skill" ? command.key.slice("skill:".length) : null;

  return {
    name: primaryAlias.slice(1),
    description: command.description,
    argument_hint: formatArgHint(command.args),
    aliases: aliases.map((alias) => alias.slice(1)),
    category: source === "skill" ? "skills" : (command.category ?? "other"),
    scope: command.scope,
    source,
    skill_name: skillName,
  };
}

function resolveAgentIdFromQuery(agentIdRaw: unknown): string {
  if (typeof agentIdRaw !== "string") {
    return "";
  }
  return normalizeAgentId(agentIdRaw);
}

export function commandsRoutes(_config: BridgeConfig): Router {
  const router = Router();

  // GET /api/commands?agentId=main
  router.get("/commands", asyncHandler(async (req, res) => {
    const cfg = loadConfig();
    const requestedAgentId = resolveAgentIdFromQuery(req.query.agentId);
    const knownAgents = listAgentIds(cfg);
    const agentId = requestedAgentId || knownAgents[0] || "main";

    if (requestedAgentId && !knownAgents.includes(agentId)) {
      res.status(400).json({ detail: `Unknown agent id: ${requestedAgentId}` });
      return;
    }

    const workspaceDir = resolveAgentWorkspaceDir(cfg, agentId);
    const skillFilter = resolveAgentSkillsFilter(cfg, agentId);
    const skillCommands = listSkillCommandsForWorkspace({
      workspaceDir,
      cfg,
      skillFilter,
    });

    const commands = listChatCommandsForConfig(cfg, { skillCommands })
      .map(toCommandInfo)
      .filter((command): command is CommandInfo => command !== null);

    res.json({
      agentId,
      commands,
    });
  }));

  return router;
}
