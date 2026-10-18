# AI-D32：日期依据标签运维修正

完成时间：2026-10-18T16:07:06.656494+08:00。仅所属本地环境，AI-T15/AI-T16运维修正单元通过，不代表完整SDD全部完成。

用户“做了，当做后期数据运维吧”。这项作为后期运维修正执行。原M05实际日期正确、basis错误；原失败证据及SHA保留，不重写旧快照。

## 变更与边界

仅修改`portal/baichuan_assistant_worker.py`的SYSTEM日期提示：basis表示业务含义，不是谁输入日期；明确作为有效性基准的投标日/开标日/投标截止日用tender_date，普通指定日期用user_date，无指定日期用query_date，追问未改日期时完整继承。普通发证日期不推断投标日，多日期歧义必须保留unresolved。

无事后强制改标签、日期值或模型原始响应；仍由原条件编译器及确定匹配检查。历史快照不重写，未知不提升。prompt不能证明所有任意表达都正确，以下只报告实际三个样本。

## 本轮实质验证

43模块571项当前源码回归PASS，288.005秒，0skip，78冻结输入保持；含解析器依赖。不是重复计入前版571。无新增镜像实现测试，日期理解通过下列真实模型用例验证。

| 场景 | 实际日期 / 依据 | 确认 / 候选 | 接口完成耗时 | 状态 |
| --- | --- | --- | --- | --- |
| M05 | `2027-06-30` / `tender_date` | 0 / 1283 | 3.240s | PASS |
| D32-generic | `2027-06-30` / `user_date` | 0 / 1283 | 3.655s | PASS |
| D32-followup | `2027-06-30` / `tender_date` | 0 / 1283 | 3.571s | PASS |

M05沿用原冻结失败原文和预期；普通日期对照仅删除“投标日”，预期user_date；M05同会话追问仅修改条数，日期及tender_date保留。全部1283企业ID唯一且齐全，未来日期有效性缺证据仍0确认/1283未知候选；逐项引用、输出字段/条数、结果API、会话刷新读取均校验通过。没有把资料未知判满足。

真实3次调用，输入4172 / 输出368 tokens，0自动重试；query模型次数预算仍无上限，三条是验收场景数量。既有共享网关4/min未变。

## 本地加载与保护

2026-10-18T16:06:11.457429+08:00在线备份后仅重载所属portal/worker。原前端163文件与PID21632、两个网关保持，4健康端点200；加载无迁移、seed、企业查询或模型探测。真实验收只新增2会话/6消息/3任务/3快照/3模型日志及必要正常认证记录。新增auth session实际0，用户其他字段保持。所有旧企业、资质、证书、资料、历史业务/研究/快照/任务/模型/旧session保持；原Excel与试运行数据库hash保持。无前端编辑/构建/重启、独立企业研究或维护写库、远程操作、提交推送。

原页面未再次重复验收，本轮使用实际业务API与会话刷新读取；此前UI证据仍仅属其原版本范围。全查询5秒目标及剩余性能/兼容矩阵未完成，不因此标完整AI-T15/16/17为DONE。自动化保持PAUSED。

## 私有证据及恢复点

| 证据 | 相对仓库路径 | SHA256 |
| --- | --- | --- |
| 当前回归 | `.runtime/baichuan-ai-local/night-acceptance-20261018/d32-date-basis-operations/regression/receipt.json` | `4b18430431d3c67cfb22aab8b26cc2d026ee0006d17867a7ab350391d8e4c472` |
| 备份加载 | `.runtime/baichuan-ai-local/night-acceptance-20261018/d32-date-basis-operations/load/receipt.json` | `0d7913f817bc1bbc904c224bd35ff4622cbc29ef909da7cfbdd99d813d631091` |
| 真实日期验收 | `.runtime/baichuan-ai-local/night-acceptance-20261018/d32-date-basis-operations/api/receipt.json` | `0f3765437b850bff6659dd0e983f1074eee29738cd6bb6be21edfc693d13aa19` |
| 只读收尾 | `.runtime/baichuan-ai-local/night-acceptance-20261018/d32-date-basis-operations/closure.json` | `c159aa278150e989c567cae515ab796a8a05f420b4507988683b15e9b1a10b13` |

恢复从本单元closure及checkpoint开始。M05已修复并取得新证据，不重做历史通过样本；下一步连续检索吞吐及剩余验收，信息补全继续延期。
