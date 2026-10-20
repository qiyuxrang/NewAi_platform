# GM 纯文字默认等级与原生刷新恢复：独立实际验收

- 任务：AI-T08 / AI-T13 / AI-T15 / AI-T17 的 GM 剩余实际矩阵缺口。
- 本文件初始状态仅准备；随后根通知静止窗口，唯一实际执行通过。此前 GM 表格失败回执和分项结果保持。
- 此单元不重复表格、上传、PDF、扫描或 product 验收。验证文字中的裸二级默认精确与 GM 原 UI 的真实刷新恢复；不验证“及以上”。

## 固定脚本与边界

私有脚本：`.runtime/baichuan-ai-local/night-acceptance-20261018/gm-text-default-inflight-recovery.py`。

修正后准备版本 SHA256：`cfab37e1234f6f2f35c7f4fb2c098b694c5c66b63915a690a62661fbc82ce1d2`。

固定文字：投标人须有电子与智能化工程专业承包二级；制造商须有CCRC二级；ITSS二级只作优先项。

唯一原 UI 查询、技术验收预期一次模型调用、零自动重试、零上传/导出/研究。该单元技术调用数约束不改变用户夜间任务无额外人工用量上限的指令。默认模式仅创建私有准备回执，无 SQL/HTTP/模型调用。业务模型和前端均不改动。

提交时原生 UUID 在请求放行前写入回执；收到 202 即保存真实 owner 的助手 localStorage key/cid，且不保存认证 token。实际在途关闭、原列表操作、后台完成后真正 page.reload，不注入 cid；读回原生存储并恢复同一 cid/jid/sid 后才审阅编译语义。任何失败保留原回执，不重发。新模型/会话/消息/任务/附件/快照及 Django session 增量与四字段快照 SHA 单独留证。

## 已执行的隔离与默认检查

解释器：`C:/Users/YLJJT/AppData/Local/Python/pythoncore-3.14-64/python.exe`。

命令：`python test_gm_text_preparation.py`（在对应私有目录下；实际使用上述绝对解释器）。首轮结果：9 tests / 0.096s / OK / 0 skip。准备审阅后新增全库快照数量边界检查，第二轮：10 tests / 0.101s / OK / 0 skip；AST 与 compile 均通过。

检查包含默认模式在 SQL、DNS、socket、execute 均被禁止时成功；默认再次运行保留已有失败和 native UUID；禁止重放已尝试任务；两个裸二级精确等级及制造商/投标人主体；ITSS 不提升为硬条件；合法当前文字引用与他人/附件引用拒绝；存储 owner/cid 隔离；真实 reload 和存储取证先于语义断言；完整保留全部 20 个既有快照，拒绝把 14 个夜间子集或重复 ID 当作完整 baseline。

准备审阅发现首版错误地把 14 个受控夜间快照当作全库数量；根只读核实实际全库 20（夜间 14 + 原有 6）。这是尚未执行的验收器前置断言错误，默认零调用检查看不到真实总数，不能据此记业务失败。执行前已修正为完整 20 个 ID，同时 inventory 继续保护全部原有快照内容；原首版 SHA `bb5ad767adcc488e80b183873741fa01016014e53542674f4fafcc953893c243` 与首轮独立检查收据仍保留。

实际运行脚本默认模式：`prepared_not_executed`，SQL 0、HTTP 0、模型 0。私有状态目录为 `gm-text-default-inflight-recovery/`，其中 `receipt.json` 保留空 actions / 空 request_id；原生 request_id 只能在真实 UI 首次提交时捕获。

## 实际验收

根审阅修正版 SHA 后通知静止窗口。2026-10-18 01:50:47–01:50:57（+08:00），原 UI general_manager 唯一查询 PASS，无自动重试。原始助手默认收起；真实 queued 时收起后，原手工搜索“陕西航天信息”实际显示一行；后台完成后真正 page.reload，再打开自动恢复同一 cid/jid/sid，固定快照列表可查看并返回原手工筛选。4ms 显示“提交中”及输入禁用反馈。

202 后于 01:50:47.955 保存 native assistant key/cid；刷新前 01:50:55.189、刷新后 01:50:56.370 三次原生存储完全一致，没有注入 cid。存储只含助手 key/cid，不保存 token；先完成实际刷新与取证，再审阅条件。模型 22 一次 success，5093ms，1122 输入 / 451 输出 token；两处裸二级均 grade_exact，电子投标人 / CCRC 制造商，ITSS exact2 仅 should，三项均引用真实本轮用户消息。

会话 `f0713998-9ab9-4be6-a9fa-eea97994f8ec`；任务 `6bdbc79a-ec1f-4ca3-934a-a1ee29cd351c`；快照 `e1098dd0-7111-4846-9694-5a20cdf244aa`。native request UUID `ceb04fb8-aff5-4c6c-8210-aaa35e0ec67c`。1283 候选 / 0 确认 / 0 排除，未触发研究；此结果不把未核实证书或制造商条件认定满足。

原公司/资质/人员、全部 20 个旧快照及其旧会话、任务/附件、角色/账户/证书/导出均保持；163 前端 SHA 不变。认证 Django session 34→34，新增加 0、旧行内容保持。新增仅会话 1、消息 2、任务 1、快照 1、模型日志 1；附件/导出/研究 0。

私有实际证据在同一输出目录：receipt.json、native-assistant-storage-after202.json、post-readonly-receipt.json、independent-post-readonly-audit.json、closed-original-list.png、recovered-exact-fixed-snapshot.png。独立脚本 gm-text-post-readonly.py 通过 RO 重读核对四字段快照 SHA、全部旧快照、catalog、模型/会话/来源，额外 HTTP/模型均 0。

本次刷新 PASS 仅属于此新纯文字会话；旧 GM 表格原 context 的刷新仍 NOT_RUN，旧 FAIL 回执不改。本次不验证 GM DOCX 裸二级默认或明确及以上，也不外推其他未执行场景。
