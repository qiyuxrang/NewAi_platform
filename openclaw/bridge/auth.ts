import { createHash, timingSafeEqual } from "node:crypto";
import type { IncomingMessage } from "node:http";
import type { Duplex } from "node:stream";
import type { RequestHandler } from "express";

function authorized(request: Pick<IncomingMessage, "headers">, token: string): boolean {
  if (!token || token === "dev-token") return false;
  const header = request.headers.authorization;
  if (!header?.startsWith("Bearer ")) return false;
  // Hash both sides so token comparison always uses equal-sized buffers.
  const digest = (value: string) => createHash("sha256").update(value).digest();
  return timingSafeEqual(digest(header.slice(7)), digest(token));
}

export function bridgeAuth(token: string): RequestHandler {
  return (request, response, next) => {
    if (!authorized(request, token)) {
      response.set("WWW-Authenticate", "Bearer").status(401).json({ detail: "Unauthorized" });
      return;
    }
    next();
  };
}

export function authorizeBridgeUpgrade(request: IncomingMessage, socket: Duplex, token: string): boolean {
  if (authorized(request, token)) return true;
  socket.end("HTTP/1.1 401 Unauthorized\r\nWWW-Authenticate: Bearer\r\nConnection: close\r\nContent-Length: 0\r\n\r\n");
  return false;
}
