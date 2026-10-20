> 来源记录：以下为较早 NewAi_platform 工作区的改造和检查记录。合入完整业务版本后的结果以 [整合检查](merge-newai-20261020.md) 为准，不能把旧记录直接当成本次迁移验收。

# 架构改造验证记录

日期：2026-10-20。架构与升级操作见 [平台架构](platform-architecture.md) 和 [Cloud 部署说明](../deploy/cloud/README.md)。

## 改动范围

- 复用现有业务后端和 Django 管理后台，新增三张授权表：业务域策略、文档授权、项目资料成员。支持个人、角色、部门、项目范围，区分查看、AI 使用与下载。
- 产品与工程知识检索接入统一授权，校验请求与响应的文档范围，执行前后复核；产品报告来源保留原审批与当前授权的交集。
- 模型 Provider 增加内部/外部处理属性，路由增加允许外部处理策略；候选模型、准备发送、返回结果和流式输出均执行当前授权检查。
- 修复选择模型至预留调用之间的撤权缺口：账号停用、会话/授权版本变化、角色和模型选项撤销，均在发送消息前拒绝。
- MCP 增加助手正文导出许可和三处授权版本检查；SSE 连接复核账号、绑定与运行环境变化。
- 新增 `0036`、`0037` 迁移及精确范围导入命令；生产无数据库策略即拒绝知识访问。未新增运行服务、队列组件或依赖声明。

## 隔离环境

业务测试使用 Windows Python 3.13.9、Django 5.2.17；读取已有测试解释器，不修改其安装目录。缺少的 PostgreSQL 驱动按仓库锁定版本安装到本仓库 `.runtime/architecture-tests-dbdeps`，仅对测试命令设置 `PYTHONPATH`。

真实 PostgreSQL 测试使用临时 `postgres:16` 容器（16.15），只绑定本机随机端口，无既有数据卷；所有账号和数据均为合成测试数据。测试不加载私有 `.env`，不连接现有业务数据库。

验证结束后已停止并自动移除该临时容器，并通过任务标签查询确认无残留容器。

平台测试使用本仓库独立 `.runtime/architecture-tests-platform` 环境，补齐项目已声明依赖，实际 MCP 1.30.0、FastAPI 0.150.0。此环境用于 SDK/ASGI 与模拟上游测试，不代表 Cloud 锁文件镜像已完成验证。

## 结果

| 检查 | 结果及边界 |
| --- | --- |
| PostgreSQL 全量迁移至 0037 | 成功，含真实外键、唯一与接收对象检查约束 |
| PostgreSQL 0035 存量配置升级 | 合成旧 Provider/模型/路由经 0036/0037 后保持原值；Provider 为 external、路由仍允许外部处理；没有自动生成资料授权 |
| `makemigrations --check --dry-run` | 无差异；Django 测试系统检查无问题 |
| 第一组业务回归 | 249 项，247 通过、2 跳过；覆盖统一授权、产品知识与报告检索、模型后台/选择/网关、工程 API/授权、readiness |
| 扩展业务回归 | 139 项首次 128 通过、1 跳过、10 失败；10 项均缺少本地 Mermaid 构建清单，真实构建后逐项复测全部通过 |
| 模型发送前复核最终 PostgreSQL 回归 | 路由、网关、边界、pacing 101/101 通过；Agent 适配 11 项补齐既有模块搜索路径后 11/11 通过 |
| SQLite 真实文件数据库并发预留 | 修正 fixture 后 8/8 通过，覆盖竞争写锁、配额、限流和超时；未跳过新授权检查 |
| 平台持续连接 | 31/31 通过，含已建立连接的失效与清理 |
| 受控 MCP | 18/18 通过，使用真实 SDK/ASGI、模拟业务上游，覆盖拒绝、撤权与不返回正文 |
| Cloud 部署包检查 | `python deploy/cloud/validate_package.py`：8/8 通过；含备份脚本模拟，不等于真实恢复演练 |
| Mermaid 构建与现有安全检查 | frozen lock 安装、`pnpm build` 成功；`pnpm test` 6/6 通过 |
| 格式检查 | `git diff --check` 通过 |

上述组之间有重叠，不相加为独立用例总数。第一组中两项跳过为未配置真实工程 CLI；扩展组一项为仅适用于 SQLite 的锁升级测试，在 PostgreSQL 环境按原测试设计跳过。

扩展组包含产品 LangGraph 编排、worker 事务与恢复、Agent 来源权限、人事筛选 API 和人事模型选择。首次十项失败均指向 `product_assets/mermaid-runtime/dist/runtime-manifest.json` 缺失；按仓库原构建命令生成实际产物后，复测十项原失败用例通过，没有修改测试预期或生成伪清单。构建产物与依赖仍为 Git 忽略文件。

最终模型组首次 Agent 适配 11 项因测试命令未包含 `services/business` 搜索路径而失败；该目录提供已有 `model_gateway.agent_protocol`。加入与 Cloud Dockerfile 相同的模块目录后 11 项全部通过，没有更改适配器或测试断言。

## 复现入口

业务命令从 `services/business/backend` 执行，须显式设置测试用 `PORTAL_SECRET_KEY`、`PORTAL_DEBUG=1`、`PORTAL_HTTPS=0` 和自己新建的独立测试数据库参数。`PYTHONPATH` 须包含 `services/business` 绝对路径以加载原模型协议模块；若驱动装在隔离 target 目录，同时保留该路径。不要加载线上环境或复用业务库。

```powershell
python manage.py migrate --noinput
python manage.py makemigrations --check --dry-run
python manage.py test portal.tests.test_knowledge_access portal.tests.test_product_knowledge_service portal.tests.test_product_knowledge_api portal.tests.test_product_retrieval portal.tests.test_model_admin portal.tests.test_model_processing_boundary portal.tests.test_model_gateway portal.tests.test_model_selection portal.tests.test_engineering_knowledge portal.tests.test_engineering_knowledge_acl portal.tests.test_engineering_api portal.tests.test_production_readiness --noinput
python manage.py test portal.tests.test_product_workflow portal.tests.test_product_worker portal.tests.test_product_worker_transactions portal.tests.test_agent_source_permissions portal.tests.test_hr_screening_api portal.tests.test_hr_model_selection --noinput
python manage.py test portal.tests.test_model_processing_boundary portal.tests.test_model_gateway portal.tests.test_model_selection portal.tests.test_product_model_pacing portal.tests.test_agent_model --noinput
```

扩展组运行前，从 `services/business/backend/portal/product_assets/mermaid-runtime` 执行：

```powershell
pnpm install --frozen-lockfile --ignore-scripts
pnpm build
pnpm test
```

从仓库根目录、使用已安装声明依赖的隔离 Python 执行平台检查：

```powershell
python -m unittest discover -s platform/tests -p 'test_runtime*.py'
python -m unittest discover -s platform/tests -p 'test_ragflow_mcp.py'
python deploy/cloud/validate_package.py
```

## 生产验收尚未完成的项目

本次没有启动或重启业务服务，没有迁移真实业务数据，没有向真实模型或 RAGFlow 发送资料，没有启用 DeepAgents 原生 Runtime 或正式发布。模型和知识服务上游在业务测试中被模拟；真实 PostgreSQL 能证明迁移和事务执行，不能证明外部服务的租户隔离、召回质量或供应商内部处理承诺。

上线前仍须在目标 Linux 环境完成镜像冷构建、TLS/网络出口、真实授权资料联调、文档及简历/报价业务验收、容量压测和一致备份恢复。生产迁移必须先导入或配置文档授权；新策略默认关闭助手正文导出，既有模型路由为兼容默认仍允许外部处理，敏感用途需显式改为内部专用。现有审批及 `release_approved=False` 不因本次测试通过而解除。
