# RAGFlow MCP 只读核查

核查日期：2026-10-08。未重启、启动或修改现有 RAGFlow 容器，未访问知识库数据或输出运行环境密钥。

## 当前状态

容器 `ragflow-ragflow-cpu-1` 的 `/ragflow/VERSION` 为 `v0.27.0`，启动参数仅有 `--enable-adminserver`。宿主机 `19880 -> 80` 是网页入口，`19982 -> 9382` 虽已映射，但容器 `/proc/net/tcp` 只有 `80、9380、9381` 在监听，MCP 尚未启动。

## 启用入口和参数

实际入口 `/ragflow/entrypoint.sh:18-31,73-84,234-247,333-335`：正确开关是 `--enable-mcpserver`，默认只绑定 `127.0.0.1:9382`。对容器端口映射开放还需 `--mcp-host=0.0.0.0`。多用户应选择 `--mcp-mode=host`，请求头使用 RAGFlow API token。

后续维护时可将下列参数并入原启动配置，并保留原有服务参数和数据卷；此处仅给出配置，不执行：

```text
--enable-adminserver
--enable-mcpserver
--mcp-host=0.0.0.0
--mcp-port=9382
--mcp-base-url=http://127.0.0.1:9380
--mcp-mode=host
--no-transport-sse-enabled
```

原生传输入口是 `/mcp`（Streamable HTTP）和 `/sse`（旧 SSE）。启用后的宿主机地址是 `http://127.0.0.1:19982/mcp`。`self-host` 模式使用一个全局 token；`host` 模式逐请求读取 Bearer token。以容器实际源码为准，并已核对 [v0.27.0 启动脚本](https://github.com/infiniflow/ragflow/blob/v0.27.0/docker/entrypoint.sh) 和 [原生 MCP 服务](https://github.com/infiniflow/ragflow/blob/v0.27.0/mcp/server/server.py)。

## 工具契约和权限边界

`/ragflow/mcp/server/server.py:535-650` 注册三个工具：

| 工具 | 主要输入 | 边界 |
|---|---|---|
| `ragflow_retrieval` | 必填 `question`；可选 `dataset_ids`、`document_ids`、分页和排序参数 | 数据集为空时会自动搜索该 token 的全部可访问数据集；文档默认为空列表 |
| `ragflow_list_datasets` | `page`、`page_size` | 返回该 token 可访问的知识库目录 |
| `ragflow_list_chats` | `page`、`page_size` | 返回该 token 可访问的聊天助手目录 |

`tools/list` 先读取 token 下的完整 dataset/chat 目录，并嵌入工具描述（源码 538-545）。因此，直接把共享 RAGFlow token 的原生 MCP 交给每个 OpenClaw，会绕过原门户按人、按文档的授权。`host` 模式的 token 租户边界不等于原门户账号授权边界。[原生实现](https://github.com/infiniflow/ragflow/blob/v0.27.0/mcp/server/server.py)

原门户 `backend/portal/product_knowledge_service.py:57-84` 按实际门户用户 ID 获取 `PRODUCT_KNOWLEDGE_AUTHORIZATIONS` 中的 dataset → 非空文档列表，并保存 session/grant/revision；`:406-477` 强制发送这些 dataset/document IDs，再验证每个返回 chunk 的身份。`product_knowledge_api.py` 在请求、检索返回、模型输出前持续复核授权。工程接口也保留部门、本人任务检查和固定工程数据集限制；工程检索当前没有产品接口同样的逐用户文档清单。

当前最小接入是继续经绑定的真实门户会话访问 `/api/enterprise/business/product/knowledge/...` 和 `/api/enterprise/business/engineering/knowledge/...`，保留原有业务和授权检查。

如新主调度器必须使用原生 MCP 的检索能力，需要服务器端受控包装：只向模型公开 `question` 等安全查询参数；按绑定门户用户实时取可见 dataset/document 范围，覆盖为非空列表；禁止原生全目录工具和原始 `tools/list` 描述透传；返回前复核授权并验证每个 chunk 身份。RAGFlow token 保留在服务器端。产品权限可以从原门户的知识库/文档目录 API 验证，不依赖新平台自行签发的假业务身份。

## 可重复核查

```powershell
python scripts/check-ragflow-mcp.py --self-test
python scripts/check-ragflow-mcp.py --url http://127.0.0.1:19982/mcp
```

脚本只执行 MCP `initialize` / `notifications/initialized` / `tools/list`，输出状态与工具名称，不输出 token、知识库目录或工具描述。可从 `RAGFLOW_MCP_API_KEY` 环境变量读取服务器 token；握手成功仍不代表原门户文档授权已验证，脚本会明确返回该项为 `false`。
