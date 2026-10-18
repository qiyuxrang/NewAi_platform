# AI-T11：访问尝试与字段核实的计数口径

日期2026-10-17；HEAD `ef1676cd8327d693dab897c45a234ba91413884e` 加当前工作区。原表首家试查实际12项inaccessible、0可读正文、0核实，暴露兼容报告 `researched_companies=1` 和页面“已研究企业”容易被理解为研究成功的问题。

规格AI-FR07补充明确口径。保留原API及不可变历史结果，在 `coverage_report` 增量返回 `attempted_companies`（至少一字段实际记录过尝试）、`completed_company_attempts`（全部字段不再pending/failed）和 `research_coverage_basis`。原 `researched_companies/research_coverage` 是终态比例，包含inaccessible，不能代表有效来源或事实完整。正常record_batch同时保存新计数；不回写旧任务/工作项、不重查企业、不提高核实状态。

前端将兼容计数显示为“已尝试研究企业”，继续分别显示可读来源、资料建议和已核实，不把全部访问失败叫资料完成。

实际检查：

```text
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan_research portal.tests.test_baichuan_research_runtime portal.tests.test_baichuan_source_pilot
<bundled-node> --test tests/baichuan-assistant.test.mjs  (cwd=frontend)
```

后端 **38 tests /18.662s /OK /零跳过**，system check 0 issues；前端 **9/9 PASS /666.548ms**。新增实际状态转换用例覆盖未执行0、半批尝试1/完成0、全不可达尝试1/完成1/核实0，并检查job计数及口径。既有清单权限、幂等、重试、租约、搜索相关性及试查工具一并回归；没有使用本地1283库、网络或模型。`git diff --check`通过。运行服务加载和最终类型/构建检查另记，不用单测代替部署证据。

随后TypeScript实际退出0。以上前端改动/检查在用户“不要修改页面前端”指令前完成；收到新要求后已冻结，不再构建/修改前端。后端报告只读回查使用owned local_model配置、SQLite `query_only=ON` 和socket拒绝：固定1283家，attempted_companies=1/completed_company_attempts=1/attempted_fields=12/verified_fields=0；完整报告私有 `coverage-report-clarified.json`。未改原终态或研究进度，不重发网络/模型。
