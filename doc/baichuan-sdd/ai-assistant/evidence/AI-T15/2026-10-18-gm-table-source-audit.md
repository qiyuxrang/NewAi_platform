# AI-T15：GM 单次表格真实结果与两次验收器失败保留

2026-10-18。本轮没有业务代码、前端、服务或企业资料变更；根代理暂停写入提供保护窗口。

## 原始失败与唯一真实查询

首次原脚本在放行附件 POST 前错误要求 Playwright multipart post_data_buffer 包含原文件字节，实际接口不提供此文件内容。该次只有空会话 e67fc67f-a0a9-4383-8345-2b3fe9a4d90b，0 附件/消息/job/snapshot/model，native request UUID 为 null，模型总数仍20。原失败完整保留于 gm-table-inflight-recovery/receipt-original-001-multipart-guard.json，独立 post-failure-readonly-audit.json 证明没有已接收上传或在途任务。

经审阅后另一个独立 v2 脚本只执行一次：冻结文件 SHA、原生 set_input_files、服务端附件 SHA/owner/cid 三项校验后才放行唯一 query POST，不替换 payload。实际附件 SHA256 8e695f00504404e0a1953db37213cf4219227fc3b08a31ea7dd8e75f3cc3b1e2。

v2 仍保留总体 FAIL：验收器要求所有 ITSS 引用都是附件，误拒合法的本轮真实用户文字引用。没有修改失败收据，没有再调用模型。独立只读判据复核要求“每项必须包含自己实际附件行，附加引用只能是这一条真实用户消息”；没有删去逐行要求或允许任意 message 引用。

| 条件 | 实际确定条件 | 自身附件位置 |
| --- | --- | --- |
| 电子与智能化 | must、投标人、grade_exact 2 | b4，表1行2 |
| ITSS | should、投标人、grade_exact 2；不在 must | b5，表1行3；另引用本轮 user message f8405d3b-f7ed-4677-bcdd-da6f738b8182 |
| CCRC | must、制造商、grade_exact 2 | b6，表1行4 |
| 个人 CISP | 明确项目负责人个人证书未支持/无法执行，unresolved 保留，未归给投标人 | 顶层仍保留 b7，表1行5 |

固定表格 row4 原文确为“CCRC精确二级证书”；本次证明明确精确关系保持，**没有验证 GM 裸“二级”的默认关系或“及以上”范围**。旧 D23 其他角色证据不外推。

## 唯一实际增量与保护核账

| 记录 | 实际 ID/数量 |
| --- | --- |
| v2 会话，owner2/scope baichuan-ai-local | a7831579-fa0e-49c7-a9a4-a7da21809839 |
| 唯一 native UUID | 2f76e58e-2f66-4e6c-a154-4d96d8c8004e |
| job，completed | d6697013-b0da-4361-ac96-bd88e5b57573 |
| 附件，completed/7定位块 | fb0add85-5c25-411b-a593-0b04109558e5 |
| 快照 | 40857c11-f0c1-406b-94a6-ee678653f359 |
| 消息，2 | a33c104d-7e8d-40cd-900d-1b5fb5f51342、f8405d3b-f7ed-4677-bcdd-da6f738b8182 |
| ModelCallLog，新增1 | 21/success，6346ms，prompt2239/completion572 tokens；累计21 |
| 两次执行合计 | 会话+2（含首次失败空会话）、附件+1、消息+2、job+1、快照+1、模型+1、导出/研究+0 |

结果 1283 行，confirmed0/candidate1283/excluded0；job _budget_model_calls=1、sources=0、research_policy=independent_manifest_only。没有查询时联网研究、字段写入或原快照改写。

快照四字段按根核账同算法读取 SQLite 原始 condition_tree/results/counts/fact_cutoff_at 字符串，以 JSON sort_keys=True、ensure_ascii=False、default=str 后 UTF-8 SHA256：43f1af579a1eef88656d3147ac8d1e582bbe812da560edb0bc7f61af61a4b10b。截止时间原始值 2026-10-17 17:31:01.514265。

两次执行的 Django session 均实际34→34/新增0，34条旧行哈希完整不变；不是把业务会话计为认证 session。catalog/原资质/人员、原会话消息快照、旧 job/附件、研究计数、账号角色证书导出及163前端SHA均保护通过。只读补审0 HTTP/model/业务写。原生存储未捕获，自动刷新恢复 NOT_RUN，见 [UI分项](../AI-T13/2026-10-18-gm-table-inflight-partial.md)。

私有原件位于 .runtime/baichuan-ai-local/night-acceptance-20261018/ 的 gm-table-inflight-recovery/ 和 gm-table-inflight-recovery-v2/。v2 的 post-readonly-receipt.json 与 post-readonly-audit-corrected-reference-policy.json 保存精确新增 IDs、模型日志、scope/owner关联校验、逐行条件与四字段哈希。原脚本/v2默认0SQL/HTTP/model，独立7项临时/纯内存检查通过；这些隔离检查不冒充总体浏览器验收通过。
