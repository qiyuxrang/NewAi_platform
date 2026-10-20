# 查询不自动补齐策略：本地后端实际加载

2026-10-17 20:57:14.665072+08:00完成。关联AI-T08/AI-T10/AI-T12/AI-T15/AI-T16。仅本任务所属本地portal/worker，未修改远程生产。策略实现及62项隔离验证见[查询策略证据](../AI-T08/2026-10-17-query-without-auto-research.md)。

实际运行现有私有 `restart_backend_only.py --execute`，在资料首两批入库后现读inventory作为本次基线，没有使用旧恢复收据。持同一Win32进程句柄核验身份/创建时间/命令后替换portal与worker；本次未出现端口恢复故障。frontend及两个网关进程的PID/创建时间/命令不变，163个冻结源码/测试hash未变；4项HTTP健康检查200、5项服务均owned。

本次实时基线前后inventory一致：1283企业/1460原资质/1460证书/1473证据/2930修订/11会话/31消息/6快照/7导出，账号及角色密码摘要一致；无活动任务、模型日志增量0，无真实企业查询、seed、迁移或构建。源件及owned原件、副试运行双库指纹不变。搜索、研究、事实写入常驻开关均关闭。新代码路径在旧研究开关打开时也不从查询触发研究，独立维护过程与查询解耦。

这是本地运行进程加载及健康检查；没有再次调用真实模型或重做前端角色流程，不能替代尚缺的目标生产及完整联网验收。

私有收据：`.runtime/baichuan-ai-local/restart-history/backend-only-20261017-205705.json`；当前final-restart-receipt.json SHA256 `b6cae70beb3a817ae2f3388fb006c899bce1f27615a350fbf0ed407ac2a38be6`。资料实际补空/完整性独立见[首两批证据](../AI-T12/2026-10-17-independent-enrichment-first-batches.md)。
