# 用户查询不再自动补全资料

2026-10-17（Asia/Shanghai）。关联AI-T08/AI-T10/AI-T11/AI-T12/AI-T15，AI-FR06最新用户变更：“不需要用户使用的过程中自动补齐”；独立全库资料补全继续。前端按用户指令冻结。本单元仅完成后端实现及隔离验证，未重启所属本地服务，不能据此声称运行进程已加载新策略。

## 改动

`services/business/backend/portal/baichuan_assistant_worker.py:process_query` 删除自动调用 `run_query_research` 及研究后自动生成新结果修订的分支。常规文字、文件消息、连续追问、关联重试均通过该处理路径，**即使旧环境BAICHUAN_RESEARCH_ENABLED=true，也不启动搜索、正文抓取、研究提取、字段建议或全库工作项**。

新查询使用已有授权资料做确定规则匹配，固定快照标research_status=not_requested；处理完成记completed，不再因“自动研究尚未开启”误标partial。checkpoint记research_policy=independent_manifest_only，保留真实匹配计数和条件版本。恢复已提交旧快照时保持其原内容和原研究状态，不改历史或生成研究修订。文件解析不足、条件未知、候选判定及失败/等待输入机制仍由原处理路径表达，没有将unknown改为满足。

`run_one(kind=research)`、维护权限、独立manifest、固定企业/字段分母、来源安全校验、预算与研究进度接口保持原实现。旧内部研究辅助函数仍为独立模块能力，没有用户查询调用入口；没有新增日常查询自动补全开关。

## 实际隔离验证

运行环境：Windows，`.runtime/company-test/python/Scripts/python.exe`；PORTAL_DEBUG=1、PORTAL_HTTPS=0、测试专用secret，PORTAL_SQLITE_PATH显式指向`.runtime/baichuan-ai/query-policy-tests.sqlite3`，移除继承的PORTAL_DB*/PG*变量。Django实际创建独立内存测试数据库；未访问owned资料库或远程生产。

新增 `services/business/backend/portal/tests/test_baichuan_query_research_policy.py` 的7个用例：

1. 同时开启旧research、fact_write及search配置，常规查询仍只匹配现有虚构企业，未调用任何研究入口。
2. research关闭时，正常查询同样completed且没有错误的“研究关闭”缺口。
3. 经过真实附件存储/消息及共享worker路径的文件独立请求，fixture解析定位进入条件快照，研究入口无调用。
4. 同会话追问和显式Excel导出完成，没有新增research任务。
5. 原partial查询的关联重试复用持久条件，条件模型fixture调用数0，不恢复旧补查；旧研究计数作为历史保留但未增加。
6. 恢复已提交的旧partial研究状态快照，保持原快照及结果修订，不启动研究。
7. 独立manifest仍经真实run_one→process_research分派，调用受控单企业研究fixture，固定两字段记录not_found终态；企业原值不变，未核实字段不冒充已核实。

查询用例对run_query_research、_research_company、search_public_query、fetch_public_page及研究generate_for_use均设拒绝调用保护并断言0调用。条件模型和文件解析使用明确fixture，不声称本轮调用真实模型或读取真实招标文件。独立研究仅使用fixture，不发外网。

```text
manage.py test portal.tests.test_baichuan_query_research_policy --verbosity 1
```

首轮7 tests / 3.246s / OK；随后强化关联重试的条件模型调用数断言，并执行相关回归：

```text
manage.py test portal.tests.test_baichuan_query_research_policy portal.tests.test_baichuan_assistant portal.tests.test_baichuan_file_conditions portal.tests.test_baichuan_exports portal.tests.test_baichuan_research --verbosity 1
```

最终 **62 tests / 41.029s / OK，0跳过，system check 0 issues**。覆盖助手权限/条件与已有匹配、文件放宽/追问/解析、固定快照/候选/Excel、研究固定清单及权限等相关路径。静态编译与限定文件diff检查另行执行。此次没有真实模型调用、联网、企业事实写入、全局服务配置修改、运行进程重启或frontend文件修改。

后续由主执行者统一更新共享规格、任务和恢复点；需要加载运行进程时另记录实际启动及验收证据。全库研究执行与字段核实程度不因本后端策略调整发生变化。
