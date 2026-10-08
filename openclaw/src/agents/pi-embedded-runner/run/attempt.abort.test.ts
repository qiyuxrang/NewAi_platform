import type { StreamFn } from "@mariozechner/pi-agent-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanupTempPaths,
  createContextEngineAttemptRunner,
  createContextEngineBootstrapAndAssemble,
  resetEmbeddedAttemptHarness,
  testModel,
} from "./attempt.spawn-workspace.test-support.js";

const providerStreamFn = vi.hoisted(() =>
  vi.fn(() => {
    throw new Error("unexpected model request");
  }),
);
vi.mock("../stream-resolution.js", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../stream-resolution.js")>()),
  resolveEmbeddedAgentStreamFn: () => providerStreamFn,
}));

describe("embedded attempt cancellation before model startup", () => {
  const tempPaths: string[] = [];

  beforeEach(() => {
    resetEmbeddedAttemptHarness();
    providerStreamFn.mockClear();
  });

  afterEach(async () => {
    await cleanupTempPaths(tempPaths);
  });

  it.each(["before registration", "during context assembly"])(
    "does not invoke prompt when cancelled %s",
    async (phase) => {
      const controller = new AbortController();
      const contextEngine = createContextEngineBootstrapAndAssemble();
      if (phase === "before registration") {
        controller.abort("manual-cancel");
      } else {
        contextEngine.assemble.mockImplementation(async ({ messages }) => {
          controller.abort("manual-cancel");
          return { messages, estimatedTokens: 1 };
        });
      }
      const sessionPrompt = vi.fn(async () => {});
      const result = await createContextEngineAttemptRunner({
        contextEngine,
        sessionKey: "agent:product:subagent:cancelled-child",
        attemptOverrides: { abortSignal: controller.signal },
        sessionPrompt,
        tempPaths,
      });

      expect(result.aborted).toBe(true);
      expect(result.promptError).toMatchObject({ name: "AbortError" });
      expect(sessionPrompt).not.toHaveBeenCalled();
      expect(providerStreamFn).not.toHaveBeenCalled();
    },
  );

  it("blocks a fresh SDK run started after cancellation during its asynchronous preflight", async () => {
    const controller = new AbortController();
    let sdkController: AbortController | undefined;
    let streamError: unknown;
    const abortSession = vi.fn(async () => sdkController?.abort());
    let finishPreflight!: () => void;
    const preflightFinished = new Promise<void>((resolve) => {
      finishPreflight = resolve;
    });
    const result = await createContextEngineAttemptRunner({
      contextEngine: createContextEngineBootstrapAndAssemble(),
      sessionKey: "agent:product:subagent:cancelled-child",
      attemptOverrides: { abortSignal: controller.signal },
      sessionPrompt: async (session) => {
        session.abort = abortSession;
        controller.abort("manual-cancel");
        // Like SDK prompt(), a preflight await can finish after abort() found no run.
        await Promise.resolve();
        sdkController = new AbortController();
        try {
          await (session.agent.streamFn as StreamFn)(
            testModel,
            { systemPrompt: "", messages: [] },
            { signal: sdkController.signal },
          );
        } catch (err) {
          streamError = err;
        } finally {
          finishPreflight();
        }
      },
      tempPaths,
    });
    await preflightFinished;

    expect(result.aborted).toBe(true);
    expect(streamError).toMatchObject({ name: "AbortError" });
    expect(sdkController?.signal.aborted).toBe(true);
    expect(abortSession).toHaveBeenCalledTimes(2);
    expect(providerStreamFn).not.toHaveBeenCalled();
  });

  it("still aborts an active SDK run", async () => {
    const controller = new AbortController();
    const sdkController = new AbortController();
    const abortSession = vi.fn(async () => sdkController.abort());
    const result = await createContextEngineAttemptRunner({
      contextEngine: createContextEngineBootstrapAndAssemble(),
      sessionKey: "agent:product:subagent:cancelled-child",
      attemptOverrides: { abortSignal: controller.signal },
      sessionPrompt: async (session) => {
        session.abort = abortSession;
        controller.abort("manual-cancel");
      },
      tempPaths,
    });

    expect(result.aborted).toBe(true);
    expect(sdkController.signal.aborted).toBe(true);
    expect(abortSession).toHaveBeenCalledTimes(1);
  });
});
