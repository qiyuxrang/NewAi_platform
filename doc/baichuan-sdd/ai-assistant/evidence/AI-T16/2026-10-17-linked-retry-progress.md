# AI-T16 关联重试进度保留修复

日期：2026-10-17；工作区 HEAD `ef1676cd8327d693dab897c45a234ba91413884e`。修复范围同时关联 AI-T06/AI-T10 和 AI-AC13：查询研究第一次已按检查点保存完成公司，再创建关联重试，不能显示为零家、零来源和零建议。

实际重现：`retry_job` 原来复制 checkpoint/result_ref，但丢失公开 counts；`run_query_research` 从新任务 counts 初始化为 0，然后根据复制的 `query_research_done` 跳过已完成公司，因此进度归零。新增真实数据库用例先执行原代码，确实得到 FAIL：`researched_companies/research_sources/research_suggestions` 期望各为 1、实测各为 0；不是仅靠代码推断。

修改 `portal/baichuan_jobs.py` 的 `retry_job`：新建关联尝试时同时复制公开进度计数，排除所有 `_budget_*` 内部调用计数；预算仍按新尝试重新计量。checkpoint、结果引用、父尝试链和原请求哈希校验保持有效。重复相同幂等键不会再次复制覆盖新尝试。

回归用例 `ResearchRuntimeTests.test_linked_retry_retains_completed_progress_without_inheriting_attempt_budget_or_repeating_calls` 真正执行：原查询研究→保存 partial→retry_job→claim_job→run_query_research。断言公开计数保留、内部预算不继承、相同公司被跳过、模型/搜索/正文 adapter 无再次调用、证据与事实建议未重复。所有外部 adapter 使用 fixture，没有网络/模型请求。

修复后执行：

```powershell
& .runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan_jobs portal.tests.test_baichuan_research_runtime
```

结果：`Ran 30 tests in 20.012s / OK`，系统检查无问题，无跳过。使用 owned `.runtime/baichuan-checks/tests-*` 临时文件 SQLite，包含任务进程竞争与关联重试；结束销毁。没有写企业目标库或修改远程部署。

本证据只证明受测重试和原有任务/研究回归，不宣称整体 AI-AC13 或全部 AI-T16 已完成。下一步由主执行者汇总最终联合回归及目标环境缺口。
