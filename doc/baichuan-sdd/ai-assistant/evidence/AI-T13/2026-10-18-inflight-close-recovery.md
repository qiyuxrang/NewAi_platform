# AI-T13 原页面即时反馈、运行中收起与刷新恢复

实际执行：2026-10-18 01:03:36—01:03:47（Asia/Shanghai）。状态：本次单产品角色、单新文字查询 PASS。

在用户冻结的原页面和现有本地服务上，Python 3.14.7 + 已安装 Edge/Playwright 登录 product 角色，通过原输入框和发送按钮提交一次公开合成需求。未更改 frontend 文件、页面节点、样式或请求内容，未 mock 响应。原 UI 生成的 UUID 在唯一消息 POST 放行前持久保存；已执行状态禁止重发。独立准备阶段通过 AST 和拒绝 SQL/HTTP/socket 的默认模式检查，实际尝试均为 0；收到根代理明确授权后才执行。

- 原生 form submit 捕获的 `performance.now()` 为 1704ms；React 实际按钮“提交中…”及禁用输入同时可见时为 1708ms，反馈延迟 **4ms < 1s**。这是客户端可见反馈时间，不能替代 HTTP 或完整查询耗时。
- 01:03:41.035 真实 job 为 `queued`；01:03:41.072 实际点击“收起助手，后台任务继续”，面板消失且入口可见。
- 01:03:41.263 在原列表搜索“陕西航天信息”，URL 保留真实 `q` 筛选且表格为 1 行；关闭面板没有阻止列表操作。
- 面板收起期间只读轮询实际观察到 `running/planning`、`running/matching`，01:03:45.780 为 `completed`。未取消、重试或另发查询。
- 页面刷新后默认收起，手工筛选 URL 保留；再次打开显示原需求、唯一 job 和匹配结果；原浏览器 owner 隔离的 localStorage 保持相同 conversation ID。点击现有“在列表查看”显示准确固定 snapshot ID，返回手工列表后筛选仍保留。
- 实际结果为 confirmed 0 / candidate 1283 / excluded 0；不会将候选当作满足或已核实。模型日志新增 1 条（20），0 自动重试、0 导出、0 研究。
- 企业、原资质、人员、证书、角色/账号/密码摘要、旧会话/消息/快照及旧导出均保留；研究计数未变，163 个冻结前端文件 SHA 未变。测试未调用 seed/migrate/build/restart。

私有脚本：`.runtime/baichuan-ai-local/night-acceptance-20261018/inflight-close-recovery.py`，SHA256 `fc6211aeab0a0e01f1c16f1308749601abd7ddab29918ed0e531deb027bac49d`。

私有同名输出目录保存 `preparation-receipt.json`、`receipt.json`、`before.json`、`after.json`、`post-readonly-audit.json` 和两张实际截图：`closed-original-list.png`、`recovered-exact-fixed-snapshot.png`。第二张截图拍在固定快照 ID 已显示、列表正文仍“读取固定快照”时，不将该截图声称为列表正文加载完成证据；恢复后的面板结果已由真实 DOM 断言可见。

本证据仅覆盖一次真实产品角色文字查询，不代替全部角色、文件、可访问性或全库资料核实验收。新增 ID 与四字段摘要见 [AI-T15 本次只读核账](../AI-T15/2026-10-18-inflight-query-preservation.md)。本次不更改共享任务/进度/检查点，由根代理统一同步。
