# 企业平台迁移执行记录

2026-10-08。用户已明确批准执行；当前状态：完整单文件夹整合、本机启停、双用户隔离、多 Agent 并发及两条真实取消路径已完成本机验收。实际授权知识检索、全文生成和招聘完整业务链等仍未实测，不标记全面生产就绪。

## 实际部署和数据边界

- 新员工工作台：http://127.0.0.1:3080/；新网关：8080；原业务门户：8100；原模型网关：18411。
- 完整单文件夹整合已实际落在本项目：`services/business` 包含原 Django、模型网关、静态文件、前端构建产物、本机 SQLite 一致性快照和产品/标书/工程成果；`services/engineering` 包含原 engine、tools、config、integrations、data、library。原目录保留，旧五个服务已关闭；当前启用服务使用本项目代码及本项目业务快照，不同时运行两套业务服务，不复制新知识库。
- 独立 PostgreSQL：127.0.0.1:15432；PostgreSQL 和每用户 Agent 数据仍由本机 Docker named volumes 管理，Docker 的全部物理数据并未迁入项目文件夹。现有本机 Docker Desktop、Microsoft Office 是系统先决条件，RAGFlow 保留为外部服务；本次只验证当前电脑，未声称跨电脑免安装启动。
- 本地运行时包含 CPython 3.13.9、3.12.12、Node 24.14 和 Chromium 1243。五个 venv 使用项目内 base interpreter 新建后复制确切现有 site-packages 字节，并保留公开 `requirements-*.txt` 的实际安装版本；无指向原目录的 `.pth` 路径，DRF 3.16.1 等旧基线没有按旧 manifest 升级。
- 原管理员 Next.js 页面保留在 `manage_front`，本机入口 http://127.0.0.1:3081/；原用户/容器/用量/审计功能保留，新增账号创建和部门身份分配。原五个管理页面及创建/编辑/重置对话框的 11 项真实只读检查通过。包含最终文字和布局修正的生产构建通过，现以 `next start` 运行。另在真实 PostgreSQL 创建一个明确停用的验收账号，验证创建 201、重复拒绝 409、部门分配 200 和审计留痕；未映射原业务账号、未修改既有员工。布局文件原有 `setState-in-effect` lint 问题未在本次扩改。
- 已完成修改前备份：`C:\Users\BJRunner\Desktop\Aicompany_migration_backups\20261008-103602`，含原 SQLite 一致性备份（154 MB，quick_check=ok）、两个仓库的修改快照与私有配置备份。
- 为解决原登录接口缺列错误，已应用原有 portal 0030–0034 迁移。执行前确认相关人事记录没有满足归档条件的数据；未删除文件或业务记录。
- 新管理员密码仅保存在本机 `.runtime/enterprise/admin-password.txt`；不会写进说明、前端或聊天。新旧账号登录凭据相互独立，业务连接不保存原账号明文密码。

## 已验证

| 项目 | 证据与边界 |
| --- | --- |
| 真实总经理身份与业务绑定 | 使用原有总经理测试账号绑定；产品、人事、工程、工作汇总读取均 200；原私人任务与资料权限不放宽 |
| 部门界面迁移 | 复用原产品、招聘与工程页面/API；12 页只读浏览器验收，无 JS pageerror、无业务写请求、1440×900 无横向溢出；右侧滚动时侧栏固定 |
| 单文件夹启动 | 根目录 `启动项目.cmd` 已真实执行，exit=0；重复启动 PIDs 不变。随后真实执行 `停止项目.cmd`→`启动项目.cmd`，各 exit=0，PostgreSQL、8100/18411/8080/3080/3081 五个服务及产品、人事、工程三个 Worker 健康；数据卷保留，期间外部 RAGFlow HTTP 200 |
| 整合后的业务与渲染检查 | 新位置 Django focused checks 39 项、新平台后端 33 项通过；Mermaid 6 项检查和 20 张合成图的本地 Chromium 离线真实渲染 PASS，不代表生产 Docker 或完整业务文档生成通过；迁移后 12 页业务 UI 与管理员 11 项检查继续通过 |
| 员工前端最终构建 | TypeScript 检查及 Vite 生产构建通过，共 2082 modules；构建仍有既有约 854 KB chunk 大小警告 |
| 导航权限 | 总经理有三个折叠部门组；员工仅本人部门；配置入口收进设置；非管理员访问模型管理被拒绝 |
| 身份管理 | 7 项独立 SQLite 测试通过：管理员创建/分配、非法身份、重复映射、原会话失效、真实 DB 角色鉴权及审计隐私；另在真实 PostgreSQL 创建停用验收账号，创建 201、重复 409、部门分配 200、审计存在；未修改既有员工、未绑定该验收账号的原业务身份 |
| 业务代理 | 10 项测试通过：原门户会话、CSRF、映射校验、权限拒绝、下载/流响应及并发绑定变化；保留 Content-Length/幂等标识，未知长度上传用磁盘暂存，避免 Django WSGI 不支持 chunked 请求体；不给容器或 RAGFlow 平台浏览器 JWT |
| 受控知识与业务 MCP | 官方 Python MCP SDK 的 11 项协议/权限测试通过；原门户 33 项知识 API 测试通过。真实容器身份调用产品、人事、工程任务列表成功。此前创建的两个本人草稿已再次通过真实 GET 只读核对：owner=4、产品输入草稿 `DRAFT` 与人事需求草稿 `draft`、version=1，复核未创建新草稿；真实原生 Agent 调用 `department-knowledge__department_work_list` 且 isError=false。现有知识授权拒绝得到保持；成功授权检索尚待本人业务账号绑定，草稿不代表蓝图、JD 或全文生成完成 |
| 原总经理业务边界 | 5 项原 Django 领域测试通过：本人任务、HR 草稿及原授权读取、工程/台账边界 |
| Bridge 模型和事件 | 配置模型路由、凭据过滤、MCP 配置保留、父子会话交错 SSE 全帧检查通过；真实原生执行分别收到 `platform-proxy/qwen3.7-flash`、`platform-proxy/qwen3.7-plus` 回答，未知模型被拒绝 |
| 真实子任务控制 | 两个子任务同时 running、主线程继续、steer 提交及收到结果、打开结果、收到 followup 已实测。steer 返回 202 表示提交，不声称立即中断。最终镜像的 cold 轮 9 项、active 轮 11 项通过：cold 在 exec 执行前取消，traceCreated=false、execCalls=0；active 先确认 sleep75 真实 OS 进程运行再 kill，execCalls=1，100 秒后仍 killed、专用 `/tmp` 延迟写标记不存在。两轮 trace 均 passed=true、lateCompletedExec=0、lateSuccessMessages=0、lateAssistant=[]，在该 100 秒实测窗口内持续终止通过；聊天 UI 6 项通过。旧镜像迟到回复失败证据独立保留为根因记录，非当前结果 |
| 独立运行环境代理鉴权 | 最终运行镜像已构建并将两用户原卷升级，当前镜像为 `sha256:975799667247a6f6c4be90ab88b2cdab61d648b9c507765b27db91af7afb3776`；两个真实用户各有独立 Docker 容器、数据卷和动态端口（以最新 `runtime-acceptance.json` 快照为准），原生 Gateway 均连接、commands 200、44 commands、native schema 通过。两者本人令牌 HTTP 200、WS 101，无令牌 HTTP 401、另一用户令牌 HTTP/WS 401。flash/plus 真实回答与只读 MCP 三部门任务列表已有独立证据；Bridge HTTP、原生 WS、终端 WS 的鉴权检查及浏览器 JWT 剥离保留，SSE 上游 401/503 不伪装成成功流。本人数据卷保留，两账号均 ready |
| 原生主体与企业镜像 | 原 native core 镜像及企业运行镜像均已构建成功，原生 A2UI、Control UI、QA 构建通过；Bridge 使用锁定的既有 `tsx` loader，原生 Gateway 使用编译后的 `/app/openclaw.mjs`。因二次全仓编译 OOM 移除了重复编译；未进行全 core 严格二次 typecheck，不以 loader 启动或 import smoke 代替此项 |
| 取消修复的完整 core 构建 | 完整原 core 镜像 `sha256:22c18d2795c5ccbb6267c9f4980500beda9dced201232b5d28e20b2193084646` 已构建成功；6 个生产源码的镜像内 SHA256 与项目源码一致，含 `attempt.ts`（`060f728e8371a0d503193b3de9ba5856cef915d04a9e48b837341c0d67a7e1bf`）。原有 77 项 focused checks 与格式检查、新增 4 项 attempt 回归通过；scratch 中移除新增 9 行后 3 FAIL/1 PASS，验证取消后真实 prompt/provider 调用被拦。最终 Bridge 镜像已构建升级，两条真实取消路径的状态、进程延迟写和 trace 验收均通过 |
| 原工程 Worker | 原 Windows Worker 使用原 CLI 完成历史排队任务，attempt=1、无错误；真实 XLSX 36,386 字节，六表有数据，输入/输出实际 SHA256 与 DB/CLI 记录一致；结果为 `internal_draft`，未验证价格正确性或正式审批。总经理通过新代理下载该他人任务返回 404，保留原归属边界；这不等于本人任务下载验收通过 |
| 部署生命周期 | PostgreSQL 真实连接和服务探测通过；缺 Agent 镜像即时 503，Docker IO 不阻塞网关；启动幂等，停止仅校验本次记录的进程树与项目容器 |

新平台隔离后端测试合计 33 项通过。独立审查复现并修正业务绑定覆盖管理员既定映射和并发撤权的问题；条件更新后，既定映射、登录期间重分配与停用三条路径均返回 409 且不反写。通过原业务账号与真实网关调用 `product_assistant` 默认模型，HTTP 200，回答「连接正常」；它与上述原生 flash/plus 调用分别有证据，均不能代替完整文档生成验收。

验收证据均在本机 `.runtime/enterprise/`，记录各检查当时的镜像、会话或任务；下表不包含凭据文件。私有授权文件不会加入 Git。

| JSON 路径（相对 `.runtime/enterprise/`） | 可确认结果 |
| --- | --- |
| `ui-evidence/admin/report.json`、`admin-assignment-acceptance.json` | 原管理页面及对话框 11 项只读检查、真实停用账号创建/重复拒绝/部门分配与审计 |
| `ui-evidence/report.json`、`live-business-health.json` | 12 页只读业务 UI、固定侧栏、总经理业务读取与知识授权拒绝 |
| `dependency-policy-validation.json` | frozen 依赖策略、原 core 与企业镜像构建成功、Bridge loader 与未做二次全仓 typecheck 的边界 |
| `runtime-acceptance.json` | 两个真实用户容器/卷/端口、native schema、本人及交叉令牌 HTTP/WS 验收 |
| `runtime-upgrade-acceptance.json` | 最终镜像 `sha256:975799667247a6f6c4be90ab88b2cdab61d648b9c507765b27db91af7afb3776`、两账号原数据卷保留及 ready；与最新运行验收镜像一致 |
| `runtime-chat-models-acceptance.json`、`live-model-health.json` | 原生 flash/plus 真实回答、未知模型拒绝；原业务默认模型真实回答 |
| `runtime-chat-children-acceptance.json`、`ui-evidence/live-chat-report.json` | cold 轮子任务回执、并发、主线程继续、指导、followup、100 秒仍 killed 的 9 个字段为 true；UI 报告包含本轮父会话与最终 `975799…` 镜像元数据，6 项通过 |
| `stopped-child-trace-acceptance.json` | 最终镜像 cold 轮 traceCreated=false、execCalls=0、lateCompletedExec=0、lateSuccessMessages=0、100 秒 killed、passed=true |
| `runtime-chat-children-active-acceptance.json`、`stopped-child-trace-active-acceptance.json` | active 轮 11 个检查字段为 true，确认真实 sleep75 OS 进程先运行再取消，100 秒 killed、专用延迟写不存在；traceCreated=true、execCalls=1、lateCompletedExec=0、lateSuccessMessages=0、lateAssistant=[]、passed=true。实际 exec 为 `sleep 75 && printf DONE > /tmp/migration-cancel-product-f8fdc3331f3d41a896b92f03ea3aa926` |
| `stopped-child-trace-before-final-fix.json` | 旧 `7692a688…` 镜像真实失败：100 秒标签 killed，但 execCalls=7、lateSuccessMessages=1，迟到 assistant 为 `CHILD_PRODUCT_OK`、passed=false；保留失败证据，不与最新 cold 结果混用 |
| `runtime-chat-mcp-acceptance.json`、`runtime-mcp-acceptance.json` | 原生 Agent 实际调用任务摘要工具；最新只读 MCP 重跑确认 5 个工具、三部门任务列表及知识拒绝，不再包含旧草稿创建字段 |
| `existing-own-drafts-acceptance.json` | 真实 GET 只读确认两个既有草稿 owner=4、state、version=1，`no_new_drafts_created=true`；产品 task `61804a89-23b6-4c6a-916b-281d64fe5cf4`，人事 request `5e9e61a9-3305-4216-94f1-4b318aa53a01`、draft `2f19f8ff-24bf-4c18-ae09-4f2f55eb4e0c` |
| `engineering-worker-acceptance.json`、`engineering-download-acceptance.json` | Windows Worker 的六表 XLSX、大小与 SHA256、`internal_draft`；总经理下载他人任务 404 |
| `legacy-worker-idempotency-check.json`、`legacy-worker-helper-check.json` | 原 Worker 重复启动身份不变、停止仅预检、没有新增/停止 Worker 或手工数据库写入 |
| `business-bundle-snapshot.json`、`local-runtime-packages.json`、`health.json` | 原目录保留、SQLite quick_check=ok、成果/资料复制记录、五个 venv 使用项目内 base interpreter、当前五服务及三 Worker 健康 |
| `cancellation-core-source-acceptance.json` | 最终完整取消修复 core 镜像 ID、6 个生产源码 SHA256（含 attempt.ts）、`source_matches=true`；运行结论同时由上述 cold/active trace 证据确认 |
| `final-service-health.json`、`legacy-worker-process-check.json` | 员工、管理、门户、模型网关、企业网关及外部 RAGFlow 6 个 URL 均 HTTP 200；三个本项目 Worker 各 externalCount=0 |

本项目业务 Mermaid 证据另在 `services/business/.runtime/mermaid-acceptance/a5087daf7077411592ce1da91ff49d91/report.json`：20 张合成图本地离线渲染 PASS，`productionDockerVerified=false`。

## RAGFlow 地址和 MCP

用户提供 `http://localhost:19880/`。实际探测它是 RAGFlow 网页入口；当前 RAGFlow 容器没有启用原生 MCP，`/mcp`、`/sse` 返回网页或不支持 MCP initialize。

本次保留 MCP，采用 `Agent → 新平台 /api/enterprise/mcp（Streamable HTTP）→ 原业务账号授权层 → 现有 RAGFlow HTTP 检索`。每个运行环境使用自身容器令牌，服务器保管原门户加密会话和既有 RAGFlow 密钥；不会共享租户知识库密钥给全部账号。未重新导入文档、未启动新的知识库、未修改 RAGFlow 配置或数据。用户已授权 Docker Desktop 重启恢复，恢复后外部 RAGFlow 19880 HTTP 200，原有容器服务已恢复运行。

真实总经理知识请求返回 403 `scope_revoked`，符合其当前未获资料授权的状态。本机旧 `local_ragflow_tester` 保存密码已失效，未重置该账号、未增授总经理资料、未伪造登录会话。等待用户在界面绑定本人已有授权账号后进行实际检索验收；SDK 的模拟协议测试不能代替此项。

## 待完成验收

1. MCP 部门任务列表和两个本人草稿已在真实容器身份下验收，原生 Agent 实际调用任务摘要工具已通过；真正的授权知识检索仍待本人已获授权的业务账号绑定。工具不会自动批准蓝图、JD 或正式对外报价。
2. 三个原 Windows Worker 已在队列安全检查后启动，重复启动、检查及停止预检通过，PID/解释器/UTC 启动时间不变且没有重复 Worker；原工程队列实际完成。其余产品、招聘完整任务链继续验收。
3. 真正全文文档生成、简历筛选和导出完整链路、Worker 恢复及版本冲突回归未实测；目前只确认原工程 XLSX 的文件哈希。当前页面、模型回答、MCP 草稿和接口正常不代表这些生成链路已通过。
4. 对话模型选择仅作用于新助手。旧产品 Worker 使用原模型路由；HR 保留其独立选择合同；工程使用原受控报价 CLI。聊天的 `provider/model` 不能冒充旧业务的模型 UUID 和路由配置版本。
5. 原工程 CLI 已包含③④内部成本表及⑤⑥对外劳务/采购报价表的原取费算法和生成逻辑，现有 Excel 下载继续复用；`formal_pricing=False` 是当前 Portal/CLI 的草稿状态合同，不能据此判断没有对外报价算法。供应商库有多报价及 min/max/avg 取价，但当前 API 没有完整供应商对比表，也没有正式审批、定稿、发布合同。正式对外报价审批/发布未实测。本次不发明算法、不把草稿标签直接改为正式发布；实际 Worker 成果哈希已通过。该历史任务不属于测试总经理，新代理下载返回 404，符合既有归属边界；本人新任务的浏览器下载仍待实际业务验收。

原生构建的 GPU CUDA 两个可选二进制包不用于本机 API 模型试点。企业镜像内构建副本只忽略这两条 optional dependency edges，原仓库锁文件、包版本与 integrity 不变，CPU/Vulkan 和其它可选能力保留。独立 frozen/offline 解析、结构差异验证、完整依赖安装及原 native core 镜像构建均通过；企业运行镜像构建和双用户运行验收也有独立证据。Bridge 使用 loader 运行不代表全 core 严格二次 typecheck 通过。当前 memorySearch 关闭，未将本地向量目录当成已部署的公司知识库。

## 启停与恢复

从本项目根目录双击 `启动项目.cmd` 或 `停止项目.cmd`，分别调用 `scripts/start-enterprise.ps1`、`scripts/stop-enterprise.ps1`。浏览器员工入口 http://127.0.0.1:3080/，管理员入口 http://127.0.0.1:3081/。启动脚本使用项目内运行时和业务源码；完整启动、重复启动及统一停止→启动循环已实测通过，循环后 PostgreSQL、五个服务和三个 Worker 健康，数据卷保留，外部 RAGFlow HTTP 200。

本机启动脚本 `scripts/run-business-service.py` 使用 `services/business`、`services/engineering` 及迁入本项目的私有配置；旧目录仅保留，不再另行启动旧服务或重复 Worker。仅启动业务入口可显式使用 `-BusinessOnly`；`-GatewayOnly` 只重启本次网关，不触碰数据库、员工前端、管理前端或业务服务。

停止本次服务会保留容器、卷及业务数据。回滚代码优先应用备份快照；SQLite 已升级且可能产生新数据，恢复旧库前应另做最新一致性备份并确认新成果保存，不能直接覆盖或反向删除迁移数据。
