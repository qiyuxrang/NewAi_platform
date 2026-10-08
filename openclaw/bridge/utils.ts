import type { Request, Response, NextFunction } from "express";
import path from "node:path";
import { randomBytes } from "node:crypto";

/**
 * Wrap async route handlers to catch errors and forward to Express error handler.
 */
export function asyncHandler(
  fn: (req: Request, res: Response, next: NextFunction) => Promise<void>,
) {
  return (req: Request, res: Response, next: NextFunction) => {
    fn(req, res, next).catch(next);
  };
}

/**
 * Convert nanobot session_id format (e.g. "web:default") to openclaw session key.
 * Nanobot uses "web:<name>" format; openclaw uses "direct:<name>" or just the key.
 */
export function toOpenclawSessionKey(nanobotSessionId: string): string {
  // Nanobot convention: "web:default", "web:abc123"
  // OpenClaw convention: "direct:web:<name>" or we can just pass through
  // For simplicity, pass through as-is — openclaw accepts arbitrary session keys
  return nanobotSessionId;
}

/**
 * Convert openclaw session key back to nanobot format.
 */
export function toNanobotSessionId(openclawKey: string): string {
  return openclawKey;
}

/**
 * Extract text content from openclaw message content array.
 */
export function extractTextContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter((block: Record<string, unknown>) => block.type === "text")
      .map((block: Record<string, unknown>) => block.text)
      .join("");
  }
  return "";
}

/**
 * Strip OpenClaw-injected inbound metadata blocks from user message text.
 * These blocks (e.g. "Sender (untrusted metadata):") are AI-facing only
 * and should never appear in user-visible UI such as session titles.
 */
const INBOUND_META_SENTINELS = [
  "Conversation info (untrusted metadata):",
  "Sender (untrusted metadata):",
  "Thread starter (untrusted, for context):",
  "Replied message (untrusted, for context):",
  "Forwarded message context (untrusted metadata):",
  "Chat history since last reply (untrusted, for context):",
];

const SENTINEL_FAST_RE = new RegExp(
  INBOUND_META_SENTINELS.map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"),
);

export function stripInboundMetadata(text: string): string {
  if (!text || !SENTINEL_FAST_RE.test(text)) {
    return text;
  }

  const lines = text.split("\n");
  const result: string[] = [];
  let inMetaBlock = false;
  let inFencedJson = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!;
    const trimmed = line.trim();

    if (!inMetaBlock && INBOUND_META_SENTINELS.includes(trimmed)) {
      const next = lines[i + 1];
      if (next?.trim() === "```json") {
        inMetaBlock = true;
        inFencedJson = false;
        continue;
      }
    }

    if (inMetaBlock) {
      if (!inFencedJson && trimmed === "```json") {
        inFencedJson = true;
        continue;
      }
      if (inFencedJson) {
        if (trimmed === "```") {
          inMetaBlock = false;
          inFencedJson = false;
        }
        continue;
      }
      if (trimmed === "") continue;
      inMetaBlock = false;
    }

    result.push(line);
  }

  return result.join("\n").replace(/^\n+/, "").replace(/\n+$/, "");
}

/**
 * Clean a session title by removing inbound metadata prefixes.
 * Handles both:
 * - Full multi-line metadata blocks (via stripInboundMetadata)
 * - Truncated single-line titles like: 'Sender (untrusted metadata): ```json { "label": "OpenClaw…'
 *   which were already truncated by deriveSessionTitle before reaching the bridge.
 */
export function cleanSessionTitle(title: string): string {
  if (!title) return title;

  // First try stripping full multi-line blocks
  let cleaned = stripInboundMetadata(title);

  // Then handle truncated single-line titles that start with a sentinel prefix
  // e.g. 'Sender (untrusted metadata): ```json { "label": "OpenClaw…'
  for (const sentinel of INBOUND_META_SENTINELS) {
    if (cleaned.startsWith(sentinel)) {
      // Remove everything from the sentinel line up to and including the json block
      const afterSentinel = cleaned.slice(sentinel.length).trim();
      // If the rest starts with ```json, it's a truncated metadata block
      if (afterSentinel.startsWith("```json")) {
        const afterFence = afterSentinel.slice("```json".length).trim();
        // Try to find the closing ``` fence
        const closingIdx = afterFence.indexOf("```");
        if (closingIdx >= 0) {
          // There's a closing fence — take everything after it
          cleaned = afterFence.slice(closingIdx + 3).trim();
        } else {
          // No closing fence (truncated) — the whole title is metadata, return empty
          cleaned = "";
        }
      } else {
        // Sentinel present but no ```json — skip just the sentinel
        cleaned = afterSentinel;
      }
    }
  }

  // Strip leading timestamp like "[Sat 2026-03-14 23:57 GMT+8] "
  cleaned = cleaned.replace(/^\[[\w\s:+\-/]+\]\s*/, "").trim();

  return cleaned;
}

/**
 * Generate a unique file ID (12 hex chars).
 */
export function generateFileId(): string {
  return randomBytes(6).toString("hex");
}

/**
 * Sanitize path to prevent directory traversal.
 */
export function sanitizePath(inputPath: string, basePath: string): string | null {
  const resolved = path.resolve(basePath, inputPath);
  if (!resolved.startsWith(basePath)) {
    return null;
  }
  return resolved;
}
