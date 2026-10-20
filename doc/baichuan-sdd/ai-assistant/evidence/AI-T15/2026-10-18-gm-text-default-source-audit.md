# GM 纯文字默认等级、引用与新增账核对

独立新单元使用已冻结后端及原 UI；没有修改业务代码、前端、服务、企业资料或旧快照。实际执行和只读复核均 PASS，原 GM 表格验收器两份 FAIL 原件仍保留。

固定文字包含电子投标人二级、制造商 CCRC 二级、ITSS 二级仅优先项。本轮两项 must 均 grade_exact/value 2，CCRC holder=manufacturer；ITSS 位于 should、grade_exact/value 2。三项 source_refs 都是合法当前 owner 用户消息 `message:bc2723b9-8188-48ef-9701-7efefd5da59c`。未输出制造商等同投标人、未升级为及以上，也没有新增无依据企业确认。

| 新增对象 | ID / 实测 |
| --- | --- |
| conversation | f0713998-9ab9-4be6-a9fa-eea97994f8ec |
| job | 6bdbc79a-ec1f-4ca3-934a-a1ee29cd351c |
| snapshot | e1098dd0-7111-4846-9694-5a20cdf244aa |
| user message | bc2723b9-8188-48ef-9701-7efefd5da59c |
| assistant message | a0bbb617-e8a1-4871-a34d-6947bd602080 |
| native client UUID | ceb04fb8-aff5-4c6c-8210-aaa35e0ec67c |
| model log | 22 / success / 5093ms / 1122 input / 451 output |
| counts | 1283 candidate / 0 confirmed / 0 excluded |
| fact_cutoff_at 原 SQL 值 | 2026-10-17 17:50:53.993365 |

快照 condition_tree/results/counts/fact_cutoff_at 四字段 SHA256：`01b665b283670fe39dd74a65b03b5cc2225f3de4a2a7eefa424c9a0b373bc983`。编码与根一致：对原 SQL 行使用 json.dumps(sort_keys=True, ensure_ascii=False, default=str).encode()。结果明细 1283 行。实际读取的所有既有快照为 20 个，结束总数 21，不漏 6 个 pre-night 旧快照。

增量：会话 1、消息 2、job 1、snapshot 1、模型 1；附件/导出/研究 0。Django session 34→34、新增 0、旧行保持。模型持久技术计数 1，source 计数 0，研究策略 independent_manifest_only；未设置新的产品默认用量限制。

真实 202 后立即留存 native owner assistant key/cid；后台完成前关闭助手，原列表操作成功，真正刷新后同 key/cid/jid/sid 恢复。4ms 反馈、原生存储三时点一致、双精确等级均有实际证据。参见 [浏览器过程](../AI-T13/2026-10-18-gm-text-default-native-refresh.md)。

私有路径：.runtime/baichuan-ai-local/night-acceptance-20261018/gm-text-default-inflight-recovery/。其中 post-readonly-receipt.json 保存原字段哈希/明细及新 ID；independent-post-readonly-audit.json 是后续独立 RO 再读结果，0 HTTP/模型。原公司/原资质/人员、全部旧会话/20 快照、旧 job/附件、账户/角色/证书/导出与 163 前端 SHA 保护均 PASS。

范围边界：此新文字会话补齐 GM 默认裸二级及原生在途刷新证据；不倒写旧 GM 表格刷新 NOT_RUN，不重写任何失败，不补称本次验证了文件裸二级或明确及以上。
