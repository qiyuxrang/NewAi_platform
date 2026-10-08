import fs from "node:fs";
import os from "node:os";
import path from "node:path";

type Model = { id: string; name: string; provider: string };
const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};

/** Expose only configured model identities, never provider credentials. */
export function configuredModelCatalog(config: unknown): { models: Model[]; configuredModel: string } {
  const cfg = record(config);
  const providers = record(record(cfg.models).providers);
  const models: Model[] = [];
  for (const [provider, value] of Object.entries(providers)) {
    const definitions = record(value).models;
    if (!Array.isArray(definitions)) continue;
    for (const definition of definitions) {
      const model = record(definition);
      if (typeof model.id !== "string" || !model.id.trim()) continue;
      const id = `${provider}/${model.id}`;
      if (!models.some(item => item.id === id)) models.push({ id, name: typeof model.name === "string" ? model.name : model.id, provider });
    }
  }
  const defaultValue = record(record(cfg.agents).defaults).model;
  const configuredModel = typeof defaultValue === "string" ? defaultValue : record(defaultValue).primary;
  return { models, configuredModel: typeof configuredModel === "string" ? configuredModel : "" };
}

export function readConfiguredModelCatalog() {
  const home = process.env.OPENCLAW_STATE_DIR || path.join(os.homedir(), ".openclaw");
  return configuredModelCatalog(JSON.parse(fs.readFileSync(path.join(home, "openclaw.json"), "utf8")));
}
