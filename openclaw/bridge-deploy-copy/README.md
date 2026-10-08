# 企业 runtime 部署模板

本目录由 `Dockerfile.enterprise` 复制到 `/deploy-copy`。包含公司助手 main 与 product/hr/engineering 三个部门助手，保留原 deploy_copy 的 pptx、agent-browser 用户技能资产。没有固定经理转交层；独立子任务使用原生 sessions_spawn，主助手继续可独立推进的工作并验证结果。

原生配置依据是 `src/config/zod-schema.agent-defaults.ts` 与 `zod-schema.agent-runtime.ts`：所有 agent 直接允许 main/product/hr/engineering；并发 3、每会话最多 3 个活动子任务、最大派生深度 2、子任务最长 600 秒。`tools.agentToAgent.allow` 使用同样的 agent IDs，`tools.sessions.visibility=tree`。这些是运行调度限制，部门名称和提示词不赋予业务授权；工具/门户仍按实际账号校验。

`bridge-entrypoint.sh` 将 `Agents/main` 同步到 `$OPENCLAW_STATE_DIR/workspace`，其余 agent 同步到 `workspace-<id>` 并创建 `agents/<id>`；本模板不写 Windows 或相对工作区路径。入口将 defaults 补入 openclaw.json，随后 `bridge/config.ts` 合并平台模型和本人的 MCP 连接，保留 agents/subagents 配置。本模板没有模型 ID、token、门户 session 或 MCP URL。

已有个人数据卷的默认合并只补缺，不会删除旧 manager/doctor/researcher/programmer 或覆盖所有既有设置。新模板可直接用于新的个人卷；已有卷需由部署负责方制定明确迁移，不能通过模板宣称已清除旧层级。Bridge 当前的 managed built-in IDs 也需由部署负责方确保包含 product/engineering，才能使这两个 agent 的已写入模型随用户改选同步；该函数不在本模板修改范围内。

首期镜像没有 Chromium/agent-browser 或完整 Office 依赖，相关技能默认 `enabled:false`，浏览器默认关闭。保留技能的 scripts、schemas、references 和原许可证，并给 SKILL.md 增加原生 `metadata.openclaw.requires.bins` 门控；安装并验证全部依赖后才能由部署者启用。不会指示模型安装缺失软件或强制运行不存在的程序。记忆使用 builtin，默认关闭尚无配置的自动嵌入搜索。

知识只使用实际提供的受控 MCP 检索工具，不暴露全库 key、不接受模型自选库/文档。部门业务通过实际工具与平台页面进行；审批、交付、正式报价保留用户操作。没有真实可下载 artifact 时不称文档生成成功。

验证结构与实际模板文件：

```text
node openclaw/bridge-deploy-copy/check-template.mjs
```

安装完整原生依赖后，运行本仓库官方 Zod schema 和实际 Bridge 合并检查；不会启动 gateway、模型或服务，仅使用临时目录：

```text
node openclaw/bridge-deploy-copy/check-template.mjs --native
```

镜像内对应命令：

```text
node /deploy-copy/check-template.mjs --native --native-root=/app
```

结构检查输出 `nativeSchema:not_run` 时表示只验证结构，不能视为已经执行原生 schema。`--native` 若依赖缺失会失败，不会降级为成功。
