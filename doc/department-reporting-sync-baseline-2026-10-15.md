# 部门填报到总经理工作台：同步基线检查

本文件保留实施前基线；批准后的修复及实际双会话验收见[执行与交付报告](engineering-hr-workflow-execution-2026-10-15.md)。

日期：2026-10-15，Asia/Shanghai

源码基线：`ca25864361d7b3177efe8bacc6412c105f52031d`
关联方案：[部门工作流与填报汇总 SDD v1.2](engineering-hr-workflow-sdd-2026-10-15.md)

## 1. 用户确认的业务含义

- 产品事业部的项目填写入口是“售前填报”。
- 售前、工程、财务各自填报，总经理汇总查看；财务数据进入总经理财务看板。
- 本需求不是售前项目自动分发给工程、财务，不要求建立三套项目副本。
- 本版方案沿用既有发布可见性，尚未要求草稿实时公开。

## 2. 源码检查结果

| 位置 | 结果 | 解释 |
| --- | --- | --- |
| `portal/business_boards.py::_visible_board_snapshot` | 查询对应部门最新已发布台账版本 | 保存草稿不等于总经理数据更新 |
| `board`、`board_projects`、`board_project_detail` | 已有部门汇总、项目及详情读取接口 | 现有数据层可以作为修复起点 |
| `frontend/src/components/RecentProjects.tsx` | 调用文档生成任务列表 | 这个“最近项目”不会直接列出三部门填报，不应与填报汇总混淆 |
| `frontend/src/business/finance/finance-board.ts` | 调用财务看板接口 | 仍需端到端确认填报发布、代理、刷新及指标表现 |
| `frontend/src` 的项目接口调用检索 | 未检索到消费 `boards/<部门>/projects/` 的项目汇总页面 | 是本期重点检查的页面接线缺口，尚未进行真实浏览器故障复现 |
| `portal/business_boards.py::_project_groups` | 现有部门内以处理空白后的名称分组，保留原记录 | 本期聚合不得扩展为跨部门同名自动合并 |

## 3. 已执行测试

### 3.1 后端

环境：本机 `.runtime/verification/Scripts/python.exe`，Python 3.12.14、Django 5.2.18。使用任务专用进程环境，移除继承的业务配置，设置独立存储位置；测试运行于 Django 内存 SQLite 数据库，未读取业务 `.env`、未修改实际台账或账号。

执行工作目录：`services/business/backend`。

```text
<business-python> manage.py test portal.tests.test_business_projects portal.tests.test_business_ledger_workflow portal.tests.test_business_boards --noinput --verbosity 2
```

结果：28 项通过，退出码 0；报告耗时约 40 秒，系统检查无问题。

其中 `test_product_presales_edits_are_visible_to_manager_after_publishing` 验证了售前草稿不可见、编辑后仍不可见、提交发布后总经理读取到最新进展及发布版本。其余测试覆盖工程项目读取、财务已发布版本/草稿区分、更新人来源、权限及台账基本行为。

### 3.2 前端

执行工作目录：仓库根。

```text
node --test frontend/tests/manager-workspace.test.mjs frontend/tests/ledger-entries.test.mjs frontend/tests/finance-board.test.mjs frontend/tests/finance-entry.test.mjs
```

结果：26 项通过、0 失败、0 跳过，退出码 0。

范围：总经理布局与入口、台账版本及权限、财务填报发布及冲突处理、财务看板数据展示。包含组件及契约检查，不等同于双账号真实浏览器端到端验收。

完整日志保留在忽略目录 `.runtime/sdd-sync-review-20261015/`，包含 `baseline-tests.log`、`frontend-baseline-tests.log`；本报告保存可公开复查的命令与结论，不上传本机临时数据。

## 4. 结论与后续修复策略

既有专项测试通过，暂未发现必须整体替换部门台账和发布机制的证据。采用“保留现有数据生命周期，补齐总经理汇总页面、正确数据源与刷新”的优先方案。

不能据此认定整条同步链路已经验收。SDD 审批后，使用隔离环境中售前、工程、财务、总经理四类身份，完成三条填报/发布→总经理列表/详情的场景，以及财务发布→总经理财务看板场景，并覆盖平台代理。

若发现不同步：先记录失败场景与版本，区分保存、发布、读取、代理、权限和页面刷新，再修复并回归同一场景。仅在证据表明现有结构无法满足本期业务目标时局部重构；方案由实施者判断，保留决策依据与兼容验证。

当前未修改业务代码，未执行实际数据库迁移，未启动真实模型或生产业务任务，未提交或推送 GitHub。正式实施继续等待 SDD 审批。
