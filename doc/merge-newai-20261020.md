# NewAi 改造合入 MultiUserClaw：检查记录

日期：2026-10-20。目标目录：`C:/Users/BJRunner/Desktop/MultiUserClaw`。

## 范围与保存

以目标当前工作树（HEAD `b6706e58`，包含既有未提交修改）为业务基底，合入来源 `New_aiPlatform/NewAi_platform` 在 `0bf8934` 上的权限、模型边界、运维查看和 P0 交互改进。保留百川、财务、台账、产品生成、工程资料准备、DeepSeek Harness 及招采后续实现，不以较早文件整份覆盖。

两边全部 Git 管理及未跟踪非忽略文件已保存 ZIP、SHA256 清单和差异补丁，目录为 `.runtime/merge-newai-20261020-170611`；来源 14692 文件、目标 17187 文件。原目录保留且未修改。SQLite 与平台 PostgreSQL 均有迁移前备份；这些私有备份不进入版本库。

## 迁移顺序

保留旧迁移链至 `0046_baichuan_assistant_foundation`，随后导入新 `0036_model_processing_boundary` → `0037_knowledge_access` → `0038_legacy_product_visibility`。新0036的依赖指向旧0046，保留已应用的迁移名称；编号不表示两个分支的先后顺序。当前运行库已经包含旧0046和新三项记录，历史依赖一致。

新0038只添加不存在的历史字段，旧业务迁移已经创建的删除、归档等字段保持原样。没有删除迁移记录、伪造迁移或清空数据。

可复跑：

```powershell
& services/business/.runtime/main-acceptance-venv/Scripts/python.exe -B scripts/check-merged-migrations.py --snapshot .runtime/merge-newai-20261020-170611/portal-before-merge.sqlite3
```

脚本只操作临时数据库，验证全新建库、旧0046升级和当前数据库备份升级。三者通过：最终96张表，原有业务记录数和字段保留，完整性及外键检查通过，`makemigrations --check` 无遗漏。

## 自动检查

- 员工前端：既有110项测试、迁入的3项检查、TypeScript及生产构建通过；已有业务入口和未提交修改保留。
- 管理前端：生产构建通过，10页生成；BUILD_ID `aSAttlfO_nzDvUKSeebZM`。
- 平台：83项通过，3项需要隔离PostgreSQL的专项检查跳过；运行环境权限相关31项单独通过。没有对运行中的PG执行测试。
- 业务后端：安全组182项通过；业务组121项中118通过、3项跳过，包含6项新增整合检查。百川线程与独立进程任务抢占检查实际执行。跳过项为指定cloud-ocr解析器及未开启的真实Office/Node/Chromium短链；不把跳过当成通过。可用业务venv运行 `scripts/check-merged-backend.py` 复跑303项。
- 标准启动预检：通过；产品、人事、工程、百川、招采五类worker配置可启动。

## 运行验收

已使用目标 `scripts/start-enterprise.ps1` 完成切换；后续使用此目录的 `启动项目.cmd` / `停止项目.cmd`。原新目录9个服务进程已停止，目标10个进程的PID、启动时间、命令和目录均核对通过：员工端3080、管理端3081、平台8080、业务8100、模型网关18411，以及产品、人事、工程、百川、招采五类worker。五类worker启动后日志未见错误；已有数据库、搜索和用户运行容器保留。

员工入口：http://127.0.0.1:3080/ 。百川入口：http://127.0.0.1:3080/departments/product/baichuan 。管理入口：http://127.0.0.1:3081/login 。

真实浏览器使用现有产品、人事、工程、总经理账号，14页加载通过，无JavaScript异常或失败API响应。覆盖商机、百川、文档、知识助手、成果、人事JD/筛选/历史、工程报价、总经理看板、财务及部门项目。部门接口200与跨部门403/404边界通过；百川配置启用，模型、搜索、解析、导出组件配置可用，四类账号的DeepSeek Harness组件均就绪。这是配置与页面检查，没有提交真实模型任务。

实际3080提供的 `index-DYUZfwb7.js` 与目标dist SHA256一致。管理端 BUILD_ID 与本次构建一致。

切换前再次备份SQLite至 `.runtime/merge-newai-20261020-170611/portal-before-final-switch.sqlite3`；实际库迁移提示无待执行迁移，96张表的结构和行数在检查前后一致，完整性与外键检查通过。

私有证据在同一备份目录：`live-service-verification.json`、`live-verification.json`、`served-build-verification.json`、`final-database-check.json`、`migration-verification.json` 及各组测试日志。

## 边界

本次为本地代码整合与运行检查，不代表真实模型生成、Linux正式部署、生产容量或灾备演练完成。现有Cloud Compose仍需补齐百川与招采worker声明后单独验收；本地标准入口已声明五类worker。旧知识授权配置保留，不自动扩大文档权限。

Windows临时迁移检查曾因SQLite连接未关闭导致目录清理失败，检查脚本已改为显式关闭并重跑通过。随后针对遗留临时目录的清理被自动审批策略阻止，目录保留，不影响业务或迁移结果。
