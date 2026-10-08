import express from "express";
import type { BridgeGatewayClient, GatewayEvent } from "../gateway-client.js";

export function eventsRoutes(client: BridgeGatewayClient) {
  const router = express.Router();
  router.get("/events/stream", (req, res) => {
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    });
    res.write(": connected\n\n");
    // Native chat deltas contain cumulative text. Forward every event intact:
    // a single throttle buffer loses concurrent sessions and text increments.
    const listener = (evt: GatewayEvent) => {
      if (["chat", "agent", "sessions.changed", "session.tool"].includes(evt.event)) res.write(`data: ${JSON.stringify(evt)}\n\n`);
    };
    client.onEvent(listener);
    const keepalive = setInterval(() => res.write(": keepalive\n\n"), 25000);
    req.on("close", () => {
      clearInterval(keepalive);
      client.offEvent(listener);
    });
  });
  return router;
}
