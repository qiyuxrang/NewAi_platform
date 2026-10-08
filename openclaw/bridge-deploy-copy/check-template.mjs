import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const nativeRoot = process.argv.find((v) => v.startsWith("--native-root="))?.slice(14) || path.dirname(root);
const cfg = JSON.parse(fs.readFileSync(path.join(root, "openclaw_defaults.json"), "utf8"));
const ids = ["main", "product", "hr", "engineering"];
assert.deepEqual(cfg.agents.list.map((agent) => agent.id), ids);
assert.equal(cfg.agents.list.filter((agent) => agent.default).length, 1);
assert.equal(cfg.agents.list[0].default, true);
assert.equal(cfg.agents.defaults.subagents.maxConcurrent, 3);
assert.equal(cfg.agents.defaults.subagents.maxSpawnDepth, 2);
assert.equal(cfg.agents.defaults.subagents.maxChildrenPerAgent, 3);
assert.equal(cfg.tools.sessions.visibility, "tree");
assert.deepEqual(cfg.tools.agentToAgent.allow, ids);
assert.equal(cfg.memory.backend, "builtin");
assert.equal(cfg.memory.qmd, undefined);
assert.equal(cfg.models, undefined);
assert.equal(cfg.mcp, undefined);
assert.equal(cfg.browser.enabled, false);

for (const agent of cfg.agents.list) {
  assert.equal(agent.model, undefined, "Model selection belongs to Bridge/platform");
  assert.deepEqual(agent.subagents.allowAgents, ids);
  assert.equal(agent.subagents.requireAgentId, true);
  const workspace = path.join(root, "Agents", agent.id);
  for (const file of ["AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md"]) {
    const text = fs.readFileSync(path.join(workspace, file), "utf8");
    assert.ok(text.trim(), `${agent.id}/${file}`);
    assert.doesNotMatch(text, /qmd|qmd-runner|Agents\/manager|agentId\s*[:=]\s*["']?manager/i);
  }
}
assert.deepEqual(fs.readdirSync(path.join(root, "Agents")).sort(), ids.toSorted());
for (const skill of ["pptx", "agent-browser"]) {
  const text = fs.readFileSync(path.join(root, "skills", skill, "SKILL.md"), "utf8");
  assert.equal(cfg.skills.entries[skill].enabled, false);
  const metadata = JSON.parse(text.match(/^metadata: (.+)$/m)[1]);
  assert.ok(metadata.openclaw.requires.bins.length > 0);
}

let nativeSchema = "not_run";
if (process.argv.includes("--native")) {
  const require = createRequire(path.join(nativeRoot, "package.json"));
  const { createJiti } = require("jiti");
  const jiti = createJiti(import.meta.url);
  const { OpenClawSchema } = await jiti.import(path.join(nativeRoot, "src/config/zod-schema.ts"));
  const validated = OpenClawSchema.safeParse(cfg);
  assert.ok(validated.success, JSON.stringify(validated.error?.issues));
  const { writeOpenclawConfig } = await jiti.import(path.join(nativeRoot, "bridge/config.ts"));
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "enterprise-template-check-"));
  try {
    fs.writeFileSync(path.join(temp, "openclaw.json"), JSON.stringify(cfg));
    writeOpenclawConfig({ proxyUrl: "http://gateway:8000/llm/v1", proxyToken: "test-only-token",
      model: "test-model", modelIds: ["test-model"], mcpUrl: "http://gateway:8000/api/enterprise/mcp",
      modelInput: ["text"], gatewayPort: 18789, bridgePort: 18080, openclawHome: temp,
      workspacePath: path.join(temp, "workspace"), uploadsPath: path.join(temp, "uploads"),
      sessionsPath: path.join(temp, "sessions"), skillsMarketplaceRepo: "" });
    const merged = JSON.parse(fs.readFileSync(path.join(temp, "openclaw.json"), "utf8"));
    assert.ok(OpenClawSchema.safeParse(merged).success, "Bridge merged config must satisfy native schema");
    assert.deepEqual(merged.agents.defaults.subagents, cfg.agents.defaults.subagents);
    assert.deepEqual(merged.agents.list.map((agent) => agent.id), ids);
    assert.ok(merged.agents.list.every((agent) => agent.model === "platform-proxy/test-model"));
    assert.equal(merged.mcp.servers["department-knowledge"].transport, "streamable-http");
    nativeSchema = "pass";
  } finally {
    assert.equal(path.dirname(temp), os.tmpdir());
    fs.rmSync(temp, { recursive: true, force: true });
  }
}
console.log(JSON.stringify({ structure: "pass", agents: ids, preservedSkills: 2, nativeSchema }));
