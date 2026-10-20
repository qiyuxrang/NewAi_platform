# GM 文件默认精确与明确范围：独立实际单元

唯一实际执行 PASS；最初只准备，根审阅冻结 SHA 后在企业补录静止窗口通知执行。本单元没有重跑 product、PDF、扫描或旧 GM 表格，原失败及旧表格刷新 NOT_RUN 保持。

私有脚本 .runtime/baichuan-ai-local/night-acceptance-20261018/gm-file-grade-recovery.py，SHA256 `0dab452e1d62d30f7b8a6dd758e1b57cd431e9f1eb1a5f41d85d76132f2ef4df`。

新合成输入 gm-file-grade-recovery/qualification-three-clauses.docx，SHA256 `428f01bdfffdd3eb587efc2b7b3091215dfcf6be00ec995fb42d4e04a257c710`。文件只有三段：

1. 投标人须具备电子与智能化工程专业承包二级及以上资质。
2. 制造商须提供CCRC二级证书。
3. ITSS二级仅作为优先项，不属于硬性要求。

独立本地实际 parser 提取得 completed / b1–b3 / word/document.xml 段1–3，与精确原文一致。使用既有 python-docx 1.2.0 生成公开合成 fixture，无安装、无企业/内部资料；文件排他创建，避免覆盖原样本。

## 已执行准备检查

`.runtime/company-test/python/Scripts/python.exe .../test_gm_file_grade_preparation.py`：10 tests / 0.391s / OK / 0 skip。包含真实合成 DOCX 提取、默认零业务SQL/网络/模型、首次失败与UUID保存、重放拒绝、21全库旧快照保护，以及明确电子及以上、CCRC裸默认精确、制造商、ITSS仅优先、各自段引用缺失/错段/他人附件/伪造文字拒绝。AST/compile 通过。

原脚本默认实际返回 prepared_not_executed，actions为空，native UUID为空，上传/查询/模型均未运行。脚本和 fixture 均已冻结等待审核。

## 唯一实际执行契约

GM 原 UI 纯文件发送，1 次上传、1 次 query，技术预期模型 1 次，0 自动重试/研究/导出。预计增量仅 conversation1 / attachment1 / message2 / job1 / snapshot1 / model1；认证 session 按前后真实增量记录，不预设必定新增。

放行消息前核对实际服务器附件 SHA/owner/cid；原 native client UUID 提交前持久化。202 后立即保存真实 owner 的助手 localStorage key/cid，不存认证 token；真正在途收起→原列表→后台完成→原 page.reload 后同存储/cid/jid/sid 恢复，再审阅模型语义。不能借测试断言失败重新提交，也不靠人工注入 cid 补称原生刷新。

每个谓词必须引用自己的实际段：电子 grade_at_least2 / bidder 段1、CCRC grade_exact2 / manufacturer 段2、ITSS grade_exact2 / should 段3。不能借电子的“及以上”放宽 CCRC，不猜补缺失引用。1283 未核实候选仍应 0 确认。保存真实解析块、条件、全21旧快照保护、163前端SHA及专属四字段快照SHA；前端、服务、原公司/资质/人员均不改动。

## 实际结果（2026-10-18 02:07:33–02:07:46，+08:00）

执行命令为既有 Python3.14 调用 gm-file-grade-recovery.py --execute，唯一 upload1/query1/model1、0自动重试/研究/导出。实际 Model23 success，9205ms，1543 输入 / 533 输出 token。3.5ms 可见提交反馈；真实 queued 收起、原列表操作、后台完成和原 native 存储 page.reload 恢复均通过，先完成刷新再审语义。

| 对象 | 实际 ID |
| --- | --- |
| conversation | 39fa9832-7402-4437-b957-2a78a9909144 |
| job | 76ba7e93-afa8-4ca5-ade5-95298236e445 |
| snapshot | fb5fa4be-0d5f-4331-8214-f05c27dd80f3 |
| attachment | d6a2141e-0876-4839-9281-8c56574d08ef |
| user message | 545793e4-fdd3-4a30-bfcf-9a34b4263a2a |
| assistant message | ffc895d3-1d9e-4cc7-add0-2570a7c42915 |
| native client UUID | 76f223d5-447a-47e6-b10c-ee6fca92eb11 |

真实 parser completed，3段精确原文/locators 保留。电子 at_least2 bidder 仅 b1/段1；CCRC exact2 manufacturer 仅 b2/段2；ITSS exact2 bidder 位于 should，仅 b3/段3。全部 1283 候选、0 确认/排除，未借其他类别的等级关系放宽 CCRC，未把制造商证书视为投标人满足。

快照 condition_tree/results/counts/fact_cutoff_at 原 SQL 四字段 SHA256 `29ca4443401420f59403ff90bbe29ccda1cdfd3a51ad5420e50292216510c975`，按根一致编码 sort_keys=True / ensure_ascii=False / default=str。1283明细，原 fact_cutoff_at 为 `2026-10-17 18:07:43.488575`。

新增仅会话1/附件1/消息2/job1/snapshot1/模型1；Django session34→34/新增0、旧行保持。全部21既有快照（包含6个pre-night）、旧会话/任务/附件、公司/资质/人员、账户/角色/证书/导出、研究计数及163前端SHA保护 PASS。

私有目录 gm-file-grade-recovery/ 保存原 actual receipt、native-assistant-storage-after202.json、post-readonly-receipt.json、independent-post-readonly-audit.json 与两张原 UI 截图。只读独立复核第一次因 SQLite32hex 与带连字符 UUID 单侧格式不同触发验收器断言；readonly-audit-first-failure.json 原样留证，统一两侧表示后只读复核 PASS，没有新增上传/查询/模型或更改原 UI PASS 回执。

本次补齐 GM 新文件裸默认/明确范围/干净文件流程及此新会话刷新；旧表格原context刷新仍 NOT_RUN，旧 FAIL 不倒写。GM PDF/扫描、物理低置信度扫描、无模糊支持环境等未执行范围仍保持原边界。
