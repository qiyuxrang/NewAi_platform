// Run after preparing the existing private Bridge checker: node scripts/check-bridge-auth.mjs
import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dependencies = path.join(root, ".runtime/bridge-check/node_modules");
const checkDir = path.join(root, ".runtime/bridge-auth-check");
fs.mkdirSync(checkDir, { recursive: true });
fs.writeFileSync(path.join(checkDir, "package.json"), '{"type":"module"}');
fs.writeFileSync(path.join(checkDir, "tsconfig.json"), JSON.stringify({
  compilerOptions: {
    target: "ES2022", module: "NodeNext", moduleResolution: "NodeNext", strict: true,
    esModuleInterop: true, skipLibCheck: true, typeRoots: [path.join(dependencies, "@types")],
    baseUrl: checkDir, paths: { express: [path.join(dependencies, "@types/express")] },
    rootDir: path.join(root, "openclaw/bridge"), outDir: path.join(checkDir, "dist"),
  },
  include: [path.join(root, "openclaw/bridge/auth.ts")],
}, null, 2));
const compile = spawnSync(process.execPath, [path.join(dependencies, "typescript/bin/tsc"), "-p", path.join(checkDir, "tsconfig.json")], { stdio: "inherit" });
assert.equal(compile.status, 0, "Bridge auth typecheck failed");

const require = createRequire(path.join(root, ".runtime/bridge-check/package.json"));
const express = require("express");
const { WebSocket, WebSocketServer } = require("ws");
const { bridgeAuth, authorizeBridgeUpgrade } = await import("../.runtime/bridge-auth-check/dist/auth.js");
const token = "test-only-container-alice-token";
const peerToken = "test-only-container-bob-token";
const app = express();
app.use(bridgeAuth(token));
app.use(express.json());
app.all("/api/sessions", (_request, response) => response.json({ account: "alice" }));
const server = http.createServer(app);
const wss = new WebSocketServer({ noServer: true });
server.on("upgrade", (request, socket, head) => {
  if (!authorizeBridgeUpgrade(request, socket, token)) return;
  wss.handleUpgrade(request, socket, head, (ws) => wss.emit("connection", ws));
});
wss.on("connection", (ws) => ws.send("alice"));
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;

function wsStatus(endpoint, suppliedToken) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(origin.replace("http:", "ws:") + endpoint, {
      headers: suppliedToken ? { Authorization: "Bearer " + suppliedToken } : {},
    });
    ws.once("error", reject);
    ws.once("unexpected-response", (_request, response) => {
      response.resume();
      ws.terminate();
      resolve(response.statusCode);
    });
    ws.once("message", (data) => {
      assert.equal(data.toString(), "alice");
      ws.close();
      resolve(101);
    });
  });
}

try {
  for (const supplied of [undefined, "wrong-token", peerToken]) {
    const response = await fetch(origin + "/api/sessions?token=" + token, {
      method: "POST", headers: { "Content-Type": "application/json", ...(supplied ? { Authorization: "Bearer " + supplied } : {}) },
      body: "{malformed-json",
    });
    assert.equal(response.status, 401, "Unauthorized requests must fail before JSON parsing");
    assert.equal((await response.json()).detail, "Unauthorized");
  }
  const response = await fetch(origin + "/api/sessions", { headers: { Authorization: "Bearer " + token } });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { account: "alice" });
  for (const endpoint of ["/ws", "/api/terminal/ws"]) {
    for (const supplied of [undefined, "wrong-token", peerToken]) assert.equal(await wsStatus(endpoint + "?token=" + token, supplied), 401);
    assert.equal(await wsStatus(endpoint, token), 101);
  }
  for (const defaultToken of ["", "dev-token"]) {
    let nextCalled = false;
    const response = { set() { return this; }, status(code) { assert.equal(code, 401); return this; }, json() {} };
    bridgeAuth(defaultToken)({ headers: { authorization: "Bearer " + defaultToken } }, response, () => { nextCalled = true; });
    assert.equal(nextCalled, false, "Default tokens must fail closed");
    let rejection = "";
    assert.equal(authorizeBridgeUpgrade({ headers: { authorization: "Bearer " + defaultToken } }, { end(value) { rejection = value; } }, defaultToken), false);
    assert.match(rejection, /^HTTP\/1\.1 401/);
  }
  const serverSource = fs.readFileSync(path.join(root, "openclaw/bridge/server.ts"), "utf8");
  assert.ok(serverSource.indexOf("app.use(bridgeAuth(config.proxyToken))") < serverSource.indexOf("app.use(express.json"));
  assert.ok(serverSource.includes("if (!authorizeBridgeUpgrade(request, socket, config.proxyToken)) return;"));
  console.log("Bridge auth checks passed: HTTP and both WS paths reject absent/wrong/peer/query/default tokens; own token succeeds.");
} finally {
  for (const ws of wss.clients) ws.terminate();
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));
  wss.close();
}
