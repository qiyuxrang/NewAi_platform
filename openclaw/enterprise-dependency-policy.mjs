// Deployment-only profile: API models, memorySearch disabled, no CUDA GPU.
// Keep the native lock's versions/integrities and every other optional edge.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.argv[2] || process.cwd());
const excluded = ["@node-llama-cpp/linux-x64-cuda", "@node-llama-cpp/linux-x64-cuda-ext"];
const setting = "ignoredOptionalDependencies:\n" + excluded.map((name) => `  - '${name}'\n`).join("");
const workspacePath = path.join(root, "pnpm-workspace.yaml");
const lockPath = path.join(root, "pnpm-lock.yaml");
const workspace = fs.readFileSync(workspacePath, "utf8").replace(/\r\n/g, "\n");
const lock = fs.readFileSync(lockPath, "utf8").replace(/\r\n/g, "\n");

if (/^ignoredOptionalDependencies:/m.test(lock)) {
  assert.ok(lock.includes(setting), "Unexpected existing optional dependency policy");
  assert.ok(workspace.includes(setting), "Workspace and lock policy must agree");
  console.log("Enterprise CUDA optional dependency policy already applied");
} else {
  assert.ok(!/^ignoredOptionalDependencies:/m.test(workspace), "Unexpected workspace policy");
  let patched = lock;
  for (const name of excluded) {
    const edge = `      '${name}': 3.18.1\n`;
    assert.equal(patched.split(edge).length - 1, 1, `Expected one locked optional edge for ${name}`);
    patched = patched.replace(edge, "");
  }
  // Strip only the two dependency edges; package records remain pinned in lock.
  const preservedRecords = (text) => text.split("\n").filter((line) =>
    !excluded.some((name) => line === `      '${name}': 3.18.1`)).join("\n");
  assert.equal(patched, preservedRecords(lock), "Only the two allowed edges may change");
  fs.writeFileSync(lockPath, patched.trimEnd() + "\n\n" + setting);
  fs.writeFileSync(workspacePath, workspace.trimEnd() + "\n\n" + setting);
  console.log(JSON.stringify({ profile: "enterprise-api-models", excludedOptionalPackages: excluded,
    excludedOptionalEdges: 2, originalVersionsAndIntegrities: "unchanged" }));
}
