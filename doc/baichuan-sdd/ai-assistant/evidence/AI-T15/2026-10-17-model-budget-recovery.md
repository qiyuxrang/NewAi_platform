# AI-T08 / AI-T09 / AI-T15：持久条件恢复与模型调用边界

2026-10-17，所属本地工作区。关联 AI-AC05、AI-AC13、AI-AC14、AI-AC15、AI-AC17 的隔离子项。本轮功能修复及相关隔离检查通过；未执行实际模型复验、实际企业库写入、服务重启或前端修改。

最新用户指令“没有模型预算”由根代理转达：本次长任务不另加人为模型用量上限，沿用已有模型配置。此修复不收紧产品默认预算、不新增全局上限，保留原有显式任务预算、超时、防重复、有限失败重试及取消机制。下文1次限额是合成边界测试，不代表当前夜间任务预算。

## 历史失败与复现

先读本目录 `2026-10-17-real-source-natural-language.md` 及私有 `public-query-acceptance/repaired-source-receipt.json`、`verify_repaired_sources.py`。历史真实失败为：首个自然语言任务调用1次后，来源补链验收新建另一个任务；该任务保存既有条件检查点，但执行器仍持有 claim 时 checkpoint 为空的旧对象，因此再次调用模型。整验收单元实际2次超过当时人工授权1次。它不是已有 `consume_budget` 在同一任务放行超额调用的证据；第二个任务自身有独立的1次预算。该真实失败及原日志、快照全部保留，本轮没有将它改成真实模型通过。

修复前以相同形状重现：claim 返回对象后调用 `save_job(checkpoint={conditions: ...})`，不 refresh，直接 `process_query`。新增 `test_durable_conditions_override_stale_empty_checkpoint_without_model` 实际失败，进入被替换的网关后因返回值无法编译报 `invalid_model_conditions`；1 test / 0.355s / errors=1。没有真实模型调用。

## 修复范围

仅业务文件 `services/business/backend/portal/baichuan_assistant_worker.py` 新增 `_query_state`，在 `process_query` 和 `_conditions` 入口使用。它先以调用者原 fence/worker 校验当前租约、权限及预算，然后读取新持久对象并核对任务种类、owner、会话归属和部署 scope。旧对象的 checkpoint、payload 不能取代持久状态；旧执行者也不能通过 refresh 取得新 fence。解析器和模型调用均在短事务之外。

未改 jobs 的预留计数、默认预算或 retry 语义。模型调用先持久预留；若预留后进程崩溃且是否已发出无法确定，不退还调用额度并重发。显式新重试仍是原有的独立任务预算，同时保留已完成条件；已保存条件或固定快照的恢复不再重复理解。模型已经在途时取消不能追回调用，但阻止条件、快照和回复继续发布。

新增 `services/business/backend/portal/tests/test_baichuan_model_budget_recovery.py` 14个合成用例，覆盖：

- 保存条件后旧空 checkpoint、内存伪条件及伪 payload、直接条件入口，都使用当前持久状态；不意外创建导出，不改 request_hash。
- 条件提交后及快照提交后模拟进程中断、租约过期、另一执行器重领：只调用1次替代模型；原固定快照复用，消息不重复。
- 预留1次调用后崩溃：下一执行器在有限显式预算边界停止，计数不回退、无新模型、无结果且释放租约。
- 初始取消、旧 fence、撤权、会话 owner/scope 错配，以及解析完成到理解之间取消：不调用模型；无权入口也不先解析文件。
- 模型超时、非法结构：仅计费预留1次，不由 worker 自动反复执行；安全错误提示和终态保留。
- 模型在途取消/撤权：保留1次计数，后续条件/快照/助手消息不发布；显式 retry 继承持久条件、旧计数保留，新任务无需额外调用。

## 实际执行

私有运行器 `.runtime/baichuan-ai-local/model-budget-recovery/run_tests.py` 复用已审阅 `AI-T02/probe_capabilities.py` 的安全环境配置，不读部署 `.env`；临时 SQLite 从空库迁移到0046。连接创建信号逐次检查数据库路径位于本次新临时目录。主进程 DNS、socket connect、create_connection 全拒绝，模型返回均由测试替换；竞争用例的子进程由既有测试固定到同一临时 SQLite，无实际企业库或凭据。

最终命令（仓库根目录）：

```powershell
.runtime/company-test/python/Scripts/python.exe .runtime/baichuan-ai-local/model-budget-recovery/run_tests.py portal.tests.test_baichuan_model_budget_recovery portal.tests.test_baichuan_assistant portal.tests.test_baichuan_integration_review portal.tests.test_baichuan_file_conditions portal.tests.test_baichuan_query_research_policy portal.tests.test_baichuan_jobs
```

实际 **85 tests / 62.721s / OK / 0 skips**，含两个独立进程竞争去重与 claim。连同迁移/清理总耗时70.781秒。原始输出 `.runtime/baichuan-ai-local/model-budget-recovery/combined-tests.log`。此前新增11项首轮4.340秒通过；最终扩至14项包含在85项内，不能相加。

业务模块和新增测试的 `py_compile`、逐行尾部空白检查通过；`git diff --check` 通过。本项目当前新增模块本来为 untracked，故未只依赖 git diff 检查新文件。

## 未覆盖项与恢复点

本轮0真实模型调用、0公网请求、0实际企业库连接或写入、0前端改动、0服务重启；无新依赖或第三方代码。真实模型响应质量、实际目标环境加载新后端以及全库字段补齐不在此检查内，根代理另行验收。历史人工单元总调用限额不等于产品跨任意新任务的全局额度；没有新增这种全局机制或据此声明已通过。

从此处继续时可直接复跑上述临时库命令并检查私有日志与收据。共享 README/tasks/progress/checkpoint 未由本代理修改，由根代理统一登记与部署决定。
