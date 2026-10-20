# AI-T15 单次原页面查询的持久化与保护核账

实际只读复核：2026-10-18 01:06:02（Asia/Shanghai），PASS。UI 行为及边界见 [AI-T13 原页面恢复](../AI-T13/2026-10-18-inflight-close-recovery.md)。业务库只读 `mode=ro/query_only`；补审阶段 0 HTTP、0 模型、0 数据库写。

| 新增记录 | 实际 ID |
| --- | --- |
| 会话（本轮新增 session 定义为 BaichuanConversation，共 1） | `a19f4f58-2388-46a6-adea-9bba678cf673` |
| query job（1，attempts=1，completed） | `4a991eff-8444-41c2-a385-9d2af5609d07` |
| 固定快照（1） | `93d2f1ef-adeb-4c4d-86e7-00ee99784b8e` |
| 消息（2） | `7a16b96b-e842-499b-aea8-8b22056aaf81`、`a73eefff-72fd-4b7a-a243-1c89eb7ea724` |
| 原 UI 原生 client_request_id | `e8886cef-19fd-48a5-8eed-a9b512b2829c` |
| ModelCallLog（1，success） | `20`，3194ms，prompt/completion tokens 1121/270 |

模型调用增量严格为 1；job 预算 `_budget_model_calls=1`、`_budget_sources=0`。快照结果 1283 行，confirmed 0 / candidate 1283 / excluded 0。结果原文无 U+FFFD。新会话/任务/快照均唯一，原提交编号对应实际消息。没有导出、取消、重试、研究、企业字段写入或服务/前端操作。

固定快照四字段按现有 `real-query-files.py` 的算法：读取 SQLite 原始 `condition_tree, results, counts, fact_cutoff_at` 字符串，JSON 字典 `sort_keys=True,ensure_ascii=False,default=str` 后 UTF-8 SHA256：

`c3166d9fe846c0ea32acc9eea075442e2628d7afe68261c7e4105b9c5d012da4`

各原始字段 UTF-8 SHA256：

| 字段 | SHA256 |
| --- | --- |
| condition_tree | `97517ba6f933434d2afabd25dff102806dd4277037618606619d5791701968b3` |
| results | `61de6acae08b1ee49d39a6f5ce98deb115a88e0493a81ca5c2f5be1a74301938` |
| counts | `b889309c6d6e67c14859bacc19ddf6a3a64753e8593d4a46b75df11eaa7610ca` |
| fact_cutoff_at | `78c5ae43d006b7414ec639bb6f2c7764195d561338df4b331a028e0100cc81fd` |

实际前后摘要通过：Company/CompanyQualification/CompanyPerson；原有会话/消息/快照；研究 Evidence/FactRevision/Manifest/Item 与 research job 计数；账号的 ID/username/password/active/staff/superuser/department、角色/成员关系、证书及全部旧导出；163 冻结前端 SHA。

私有完整收据：`.runtime/baichuan-ai-local/night-acceptance-20261018/inflight-close-recovery/post-readonly-audit.json`；执行前后摘要与截图在同目录。首轮补审脚本把预算计数误当快照 counts 字段而断言失败；实际设计将预算存于 job.counts，已更正为只读实际 job 行并保留诊断记录，未重发查询，也未掩盖产品失败。核心 UI 运行收据从首次即为 PASS。

本次未核实任何企业资料或资质，不扩大覆盖/核实结论。根代理可把上述新增记录纳入后续全库保护基线；该文件不修改共享 SDD 状态。
