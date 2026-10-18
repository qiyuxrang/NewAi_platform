# AI-T13：GM 原页面表格、在途收起和反馈分项实测

实际窗口：2026-10-18 01:30–01:31（北京时间）。使用现有 Python 3.14、headless Edge 独立 context、原 GM 账号及原页面，不改前端/CSS/DOM实现，不修改原生请求 payload。

| 分项 | 实际结果 |
| --- | --- |
| 默认收起→打开原助手→原生上传固定合成 DOCX 加文字 | PASS；1 附件、1 query，无自动重试 |
| 原生提交的可见反馈 | PASS，4.199999988ms，实际 submit 事件至“提交中”且输入/按钮禁用的 DOM 变化 |
| 真实在途关闭 | PASS，01:30:53.684 读取 job 为 queued；01:30:53.711 收起面板 |
| 面板关闭后原列表操作 | PASS，原搜索“陕西航天信息”返回 1 行，保留实际截图 |
| 后台继续完成 | PASS，同一 job completed，生成固定 1283 行快照，1 次模型日志 21 |
| 原 context 刷新自动恢复同 cid/jid/sid | **NOT_RUN**；下述验收器断言失败发生在读取 localStorage 之前，context 已关闭且没有 storage_state。不得在新 context 注入 cid 后冒充原刷新自动恢复 |

总体脚本结果仍为 FAIL/未完成；不能用分项 PASS 改写原收据。失败原因是验收器误将 ITSS 额外的本轮真实文字引用判为无效，实际 ITSS 仍有自身表格第 3 行引用，详见 [只读判据复核](../AI-T15/2026-10-18-gm-table-source-audit.md)。原失败保留后仅做 SQL 只读审阅，没有重新提交或补跑模型。

原生 client_request_id：2f76e58e-2f66-4e6c-a154-4d96d8c8004e。会话 a7831579-fa0e-49c7-a9a4-a7da21809839、job d6697013-b0da-4361-ac96-bd88e5b57573、快照 40857c11-f0c1-406b-94a6-ee678653f359。

私有目录 .runtime/baichuan-ai-local/night-acceptance-20261018/gm-table-inflight-recovery-v2/ 保留 receipt.json、receipt-original-001-own-refs-harness.json、closed-original-list.png、before/after.json 和独立 post-readonly-audit-corrected-reference-policy.json。旧 product 的自动刷新证据仍有效，但不复制为本次 GM 表格自动刷新已通过。
