# AI-T17：当前库在线检查点副本

2026-10-18 02:15:11（北京时间），原库仍在线。根复用既有SQLite online_backup，在共享维护锁下创建新的私有副本；创建目录后先收紧当前Windows SID ACL，再生成备份文件。仅所属 `.runtime/baichuan-ai-local/portal.sqlite3` 作为RO源，禁止覆盖目标/路径转向和网络；不重启、不恢复、不回退迁移。

副本 `.runtime/baichuan-ai-local/checkpoint-online-20261018-0215/checkpoint.sqlite3`，SHA `732a829b295ad0a1dead605d2b937561dd7dc48aba55fc1d66a32d0cb08ad4be`，quick_check=ok。源复制前、备份副本、源复制后94表逐行逻辑摘要全部一致；1283企业、22快照、Model23。0原库写、网络、模型、结构变更或服务操作。

该取样固定为47批、171家397补空字段时点。其后L8等合法增量由各维护批次新的before.sqlite3和保护收据接续，不能将本副本称作包含后续全部修订；更不能还原此整库覆盖新人工值。私有receipt.json仅存表计数/hash、执行范围和备份SHA，不复制账号/密码原值到开发文档。实际脚本checkpoint_backup_0215.py；Python复用现有company-test环境、无新依赖。

这是备份可读和一致性证据，不代替完整生产故障回退或恢复演练。前端冻结，远程生产未操作，AI-T17整项未放行。
