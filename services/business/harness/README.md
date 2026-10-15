# Business assistant Harness bridge

This process runs the official DeepSeek Harness `AgentLoop`, `AgentRegistry`,
`SessionStore`, `SessionProjectionRegistry`, `SystemPrompt`, `ToolRuntime`, and
`LlmRuntime`. All Harness packages are pinned to `0.2.1-alpha.3`; Cordis is pinned
to its matching `4.0.5-alpha.2`. The lockfile uses the official npm registry.

```sh
npm ci --ignore-scripts --registry=https://registry.npmjs.org
npm test
node runner.mjs
```

Node 22.19+ or 24+ is required. The Python business service starts one process
per assistant turn and supplies existing conversation history. Harness owns
the model/tool loop and its live stream. Enterprise authorization, model
credentials, retrieval permissions, cancellation deadline, persistence, and
output filtering stay in the Python host.

Chat, knowledge, and public-search availability are reported separately. An
account with an enabled department capability can chat without document grants; knowledge tools
are registered only when its grants and retrieval configuration are available.
Scope changes still invalidate private history. Tool results and failures are
reused only within the current turn, with authorization checked on every hit.
Public queries may rearrange literal words from the current question; new words,
history, and retrieved enterprise content cannot be added to a search query.

The process reads and writes one JSON object per line. Start input:

```json
{"type":"start","question":"Question","history":[],"tools":[],"system_prompt":"Business instructions","max_model_calls":8}
```

Tools use OpenAI function schemas. The host receives `ready`, then `model`
callbacks containing `id`, OpenAI `messages`, `tools`, and optional
`tool_choice`. Answer with `model_event` using the same id and an `event`
object: `{ "delta": "text" }`, followed by
`{ "done": true, "content": "full text", "tool_calls": [], "prompt_tokens": 0,
"completion_tokens": 0 }`. `tool_calls` use OpenAI function-call objects.

For each `tool` callback, reply with
`{ "type": "tool_result", "id": "...", "result": {} }` or an `error` field.
An error is sanitized before entering Harness. The host must validate the
selected tool and arguments against its current authorization at dispatch.
Tool parameters use Harness's enforced JSON Schema subset. The bridge strips
only `minLength`, `maxLength`, `minimum`, `maximum`, `minItems`, and `maxItems`
recursively; host validation enforces the original schemas including these
bounds. Unsupported structural keywords fail closed.

Outgoing `delta` events come from real `agent/assistant-stream` text chunks.
Reasoning chunks are not published. Public text from successive model steps
is joined with a newline, and `done.answer` exactly equals the joined deltas.
`cancel`, stdin EOF, or a termination signal aborts pending callbacks and
drains the agent. Failures emit only `{ "type": "error", "code": "..." }`.

Only supplied tools are registered in the agent scope. The kernel mounts no
shell, filesystem, network tool, default profile, telemetry, log uploader,
session-file writer, loader, or plugin installer. Each process is bounded to
8 model calls, 12 host tool calls, 32 tool definitions, and 8 MiB per input line.

Upstream API evidence: commit
[`5719020`](https://github.com/deepseek-ai/deepseek-harness/tree/571902028a75c64c1d767f4ae5fd099485f0ddf0),
especially `packages/core/agent-loop/tests/agent.spec.ts`,
`packages/core/agent/src/runtime-types.ts`, and `packages/llm/llm/src/index.ts`.
