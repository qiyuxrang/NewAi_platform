# 企业知识与草稿 MCP 接入

新平台提供标准 MCP Streamable HTTP 入口 `/api/enterprise/mcp`。它使用 Python 官方 `mcp` SDK，工具调用进入现有门户知识与部门业务接口，继续使用现有 RAGFlow 和原门户权限检查。个人运行容器仅持有自己的不透明 container token；门户 session、CSRF 和 RAGFlow API key 留在服务器。

## OpenClaw 连接配置

当前仓库 OpenClaw 的 `src/config/types.mcp.ts`、`src/agents/mcp-transport.ts`、`src/agents/pi-bundle-mcp-runtime.ts` 支持顶层 `mcp.servers`、Streamable HTTP、自定义请求头以及官方客户端的初始化、列工具和调用工具。`src/agents/pi-embedded-runner/run/attempt.ts` 将这些工具加入实际 agent run。配置文件默认是 `$OPENCLAW_STATE_DIR/openclaw.json`，也可以通过 `OPENCLAW_CONFIG_PATH` 指定。

每个独立容器由服务器写入自己的配置，示例中的 token 为占位符：

```json
{
  "mcp": {
    "servers": {
      "department-knowledge": {
        "url": "http://gateway:8000/api/enterprise/mcp",
        "transport": "streamable-http",
        "headers": {"Authorization": "Bearer <this-container-token>"}
      }
    }
  }
}
```

实际地址由部署者设置，Docker 网关服务名与端口必须与部署一致。模型不能选择服务器 URL、用户、知识库、文档或 API key。不要将浏览器 JWT 或共享运行 token 写入配置。此接入适用于每人独立容器；共享进程内的全局 MCP header 无法隔离不同人的身份。`src/acp/translator.ts` 当前不接受逐会话 `mcpServers`，应由服务器预置个人配置。

## 服务端挂载与生命周期

`platform/app/ragflow_mcp.py` 导出 `mcp_http_app` 和 `mcp_session_manager`。在主应用 lifespan 的同一 task 中进入管理器，先注册原 enterprise router，再挂载子应用：

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.ragflow_mcp import mcp_http_app, mcp_session_manager

@asynccontextmanager
async def lifespan(app):
    # 保留主应用原有启动和关闭步骤。
    async with mcp_session_manager.run():
        yield

app = FastAPI(lifespan=lifespan)
# app.include_router(enterprise.router) 等原有路由必须在 mount 前。
app.mount("/api/enterprise", mcp_http_app)
```

最终路径是 `/api/enterprise/mcp`，无末尾斜杠。FastAPI 不会自动启动已挂载应用的 lifespan，必须在主 lifespan 中运行管理器一次。现有 lifespan 若使用 `AsyncExitStack`，可用 `await stack.enter_async_context(mcp_session_manager.run())`。同一个管理器不能重复启动。SDK保留 Host/Origin 防护，当前允许 localhost、127.0.0.1、gateway、openclaw-gateway、host.docker.internal；其他部署域名需由服务端显式加入。响应均为 `Cache-Control: no-store`。

## 工具与实际授权

| MCP 工具 | 唯一输入 | 原门户接口与边界 |
|---|---|---|
| `product_knowledge_retrieve` | `question`，1–2000 字符 | 按原用户 dataset → 文档授权直接检索，返回真实来源，供当前 OpenClaw 对话模型使用 |
| `engineering_knowledge_retrieve` | `question`，1–1000 字符 | 调用已有工程检索，仅原部门权限、本人已检查任务和固定工程数据集允许时返回来源 |
| `product_create_draft` | `message`，1–8000 字符 | 保存本人项目输入草稿，不读取模型指定的服务器文件，不启动生成或队列 |
| `hr_create_intake_draft` | `text`，1–8000 字符 | 本地提取招聘说明，保存本人需求和待人工审查的 JD 草稿，不调用模型或 confirm |
| `department_work_list` | `department`，枚举 product/hr/engineering | 固定路径读取本人工作列表，只返回允许的摘要字段，最多 20 条 |

工具目录只有固定名称、描述和输入 schema，没有知识库或文档目录。额外参数由 SDK schema 验证拒绝。HR 现有门户没有通用知识接口，因此没有 HR 知识检索工具；HR 草稿工具只调用现有本地提取接口。

每个 HTTP 请求经 SDK Bearer 认证：`get_container_by_token` → 当前 Container.user_id → 数据库真实 User → is_active、现有业务能力及本人加密门户会话。每次工具调用再次校验绑定，并通过原 `/api/me/` 和 `/api/modules/` 验证原门户账号。平台管理员角色不会自动授予业务权限。

产品工具调用的原 API 为：

1. `GET /api/product/knowledge/status/` 检查服务和本人授权，读取不含目录的 `authorization_revision`。
2. `POST /api/product/knowledge/retrieve/`，请求体仅有 `question`，不允许额外字段或查询参数。
3. 再次 `GET /api/product/knowledge/status/`，比较检索前、检索返回和检索后三个 revision，任何不一致都扣留来源。

原门户新增的 `retrieve` 复用现有 `endpoint`、`service.ready`、`service.retrieve(question, [], scope, config)` 和检索前后授权检查。它仅进行有边界的 RAGFlow 检索，验证每个 chunk 的真实 dataset/document 身份，生成 `S1/S2` 等引用 ID，不调用模型、不创建对话、不写数据库。`authorization_revision` 是本人完整规范 scope 的 SHA256，包括实际 dataset → 文档清单、session/grant version、知识服务 authority 和配置 revision。只有本人通过原授权及 ready 检查才能读取；返回前还会复查授权。

单纯 `available: true` 或 `/me` 的模块身份无法识别部分文档撤权，因此必须检查 revision。模型看不到 revision，包装层只返回检索状态和已授权来源。所有检查仍遵循原门户逐请求时间点的授权边界，不能保证响应完成以后发生的撤权追溯移除模型已收到的资料。

工程工具调用 `POST /api/engineering/knowledge/retrieve/`，随后读取 `/api/engineering/knowledge/` 复查任务状态。最后再次检查原门户身份，并刷新新平台 User；停用、解绑、更换映射或撤销本部门能力都会扣留回答与来源。不会透传平台 Bearer 给原门户。

源码依据：原仓库 `backend/portal/product_knowledge_service.py` 的 authorize/retrieve、`product_knowledge_api.py` 的 endpoint/retrieve/browsing_recheck，以及 `engineering_knowledge.py` 和 `engineering_api.py` 的工程知识状态与检索接口。工程权限当前没有产品接口同样的逐用户文档清单，包装层保留其现有授权边界。

两个知识检索工具只返回检索来源，由当前 OpenClaw 对话模型回答。产品知识检索不会计入原门户每人 100 个知识对话的上限，也不会额外调用一次原问答模型。按要求保留的 `service.ready` 仍验证现有产品知识服务和专用路由配置，配置不完整时拒绝检索。

## 部门草稿与工作列表

`product_create_draft` 固定调用 `POST /api/product/conversations/`，请求体为 `{message, paths: [], requested_outputs: []}`，服务端生成 UUID `Idempotency-Key`。显式空路径关闭原接口从消息中提取服务器文件路径的行为。原接口只创建 DocumentTask 和输入 revision，原模型默认状态为 DRAFT/INTAKE、pending_action 为空；产品 worker 只选择 QUEUED/过期 RUNNING，没有自动启动队列。即使原接口把 technical_solution 加入意图列表，其状态仍是 blocked/model_not_authorized。

创建必须返回 HTTP 201；200/202 不会被当成成功。随后 GET `/api/product/tasks/{id}/` 校验当前账号 owner、DRAFT/INTAKE 和版本，仅返回 task_id、version、真实草稿状态、`artifact_available:false` 与 `/departments/product/documents?task={id}` 审查链接。不会返回原任务全部正文、内部配置或审批资料。

`hr_create_intake_draft` 固定调用 `POST /api/hr/recruitment/requests/intake/`，请求只有 text。原 `hr_jd_service.create_intake` 用本地 `extract_requirements/intake_draft` 保存本人 RecruitmentRequest 和 draft JDVersion，无网关生成。创建必须返回 201，再 GET 原需求和 JD 版本接口复核本人 owner、需求关联与 draft 状态。只返回 request_id/draft_id、输入和草稿版本及 `/departments/hr/jobs` 审查页面入口；该页面当前没有按 request ID 的深链选择功能，因此 ID 独立返回供用户定位。

创建后的原门户检查、平台 User 刷新或 container token 复核若失败，不向模型释放成功回执。原门户写入可能已提交，包装层不能跨 HTTP 回滚已保存草稿；错误提示要求先在业务页面核对，避免重复创建。平台授权不因工具名、Agent 名称或平台 admin 身份扩大。

`department_work_list` 的部门参数只接受固定枚举，分别调用原 product/tasks、hr/recruitment/requests、engineering/jobs。产品过滤 owner_id、人事过滤 created_by_id 为绑定门户账号，工程原 endpoint 的 ORM 固定 owner=request.user。产品只返回 id/title/state/stage/version/updated_at，人事只返回 id/position_name/input_version/official_jd_stale/updated_at，工程只返回 id/status/region/updated_at；字符串最多 200 字符，最多 20 条并标明 truncated，不返回薪资、完整正文、检查记录、工程结果或配置。

所有业务工具复用 `bound_portal`：真实 token→Container→User→本人 session、部门能力、原 me/modules 前后检查以及最终 User/container token 复核；写请求只发送本人原 CSRF。仅保留这些固定接口，没有 approve/confirm、生成正式交付、正式报价、旧 Agent 运行或工程队列启动工具。

## 验证与当前限制

```powershell
.\.runtime\python\Scripts\python.exe -m unittest discover -s platform/tests -p test_ragflow_mcp.py
```

MCP 测试使用官方 `ClientSession` 和 `streamable_http_client`，经过 FastAPI 实际挂载路径初始化、列工具、调用工具。保留原六项知识/会话授权测试，新增业务输入草稿、固定字段/部门、201 状态、owner、写入后撤权和受限列表摘要测试。以内存 SQLite 和模拟门户验证，不创建真实业务草稿。原仓库 `backend/portal/tests/test_product_knowledge_retrieve.py` 使用真实 ORM 授权与模拟 RAG HTTP，另测真实 session/CSRF、仅本人文档范围、无模型调用/对话创建、输入限制、错误来源、响应长度限制和检索期间撤权。两组测试均不访问实际业务 DB、模型或 RAGFlow。

目前实时 RAGFlow 原生 MCP 的 `19982 → 9382` 映射没有监听服务；`19880` 是网页。以上受控 MCP 包装可使用现有门户已运行的 RAGFlow REST 链路，不需要重启旧容器或向个人容器发全库 key。实际知识问答仍取决于原账号授权、现有 RAGFlow、原问答模型与任务状态；测试通过不表示已完成实时知识问答验收。原生服务核查详见 [只读报告](ragflow-mcp-readonly-findings.md)。
