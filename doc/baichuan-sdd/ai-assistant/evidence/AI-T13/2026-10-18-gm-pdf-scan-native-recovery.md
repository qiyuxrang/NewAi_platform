# AI-T13：GM 两份 PDF 原生在途关闭与刷新

2026-10-18 02:46–02:48，两个独立 general_manager 新会话，各一次原 UI 上传和 query、一次模型，无 retry／导出／研究，完整过程与保护核账见[实际验收](../AI-T15/2026-10-18-gm-pdf-scan-native.md)。

两例均先在放行 POST 前保存原 UI native UUID，再在 202 后、模型语义审阅前保存原 owner 助手 key/cid。确认真实 queued 后收起，操作原企业搜索列表，轮询后台完成，真正刷新同一 page，默认收起再打开，恢复相同 cid/jid/sid 与固定快照，再返回原手工筛选。after202／before_reload／after_reload 助手存储一致；没有注入 cid、修改 DOM 或用户浏览器。真实提交反馈分别 4.2ms 与 3.4ms；该计时不代替首结果绘制或总体 P95。

文字 PDF cid `34f033ed-a371-4114-b469-4e3128cc6b61`、jid `854793c1-767b-48cb-bff1-ed494750b0bb`；旋转扫描 cid `14f46ade-677e-402c-8095-8fd41200a379`、jid `42da14bb-8af9-46fc-b744-43a58c8b1a8c`。私有目录 `night-acceptance-20261018/gm-pdf-scan-native/{text_pdf,rotated_scan}/` 分别保存原生存储、receipt、后审和 `closed-original-list.png`／`recovered-exact-fixed-snapshot.png`。

独立只读后审通过：企业／资质／人员和全部 22 个旧快照／旧会话保持、163 前端 SHA 保持，认证 session 实际 34→34。仅这两个新会话的在途恢复通过；旧 GM 表格原 context 刷新 NOT_RUN 及历史失败不改写。
