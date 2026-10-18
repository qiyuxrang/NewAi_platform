# AI-T12 N14A：固定20家有界具体字段复查

冻结时间：2026-10-18 03:19:27（北京时间）。冻结 selection `no_usable_retained_lead[360:380]` 实际20家，与N13 `[320:360]`、N14另一20家互斥。selection SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

每家一次具体字段/所在地查询，共20次，5组完整搜索返回及ID/意图已存。实际9次正常TLS GET，8份非空正文、8个主体；空正文1份，失败0次，旧失败host/已读URL跳过0个，0重试，每家最多2GET。搜索片段、空壳、相近主体不当正文事实。

准备3家3个原空字段候选：{"address": 2, "email": 1}，版本全部1。晟基地址、诺文科邮箱、兰特地址。桃江正文湖南与原陕西省冲突不填地址/省；华远及诺文科不同地址保留，原非空电话不覆盖；招聘手机号/邮箱排除。金蝶实际仅模板、另一个页面可见正文空，均不以搜索摘要补值。

所有来源是公开披露候选，未提升为工商或发证核验；官网提议0、证书提议0。原非空值保留。完整原HTML/可见正文、SHA、精确摘录及定位留私有目录。20行当前版本/原值RO核对通过，随后SQL/DNS/socket拒绝条件下真实 `validate_batch` PASS，三个拒绝探针PASS；固定切片/互斥/查询绑定/请求上限/39个冻结原件hash离线核账PASS。模型、业务写、前端或服务变更均0。根执行者唯一审核应用，候选不是入库或全部12字段终态。

私有恢复目录 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

- `cohort-no-lead-n14a.json` SHA256 `bc60ddef14e2d35fd4292709ecee11e5023640c8cd4aa52935b88bc47ab727fc`。
- `research-no-lead-n14a.json` SHA256 `c092b235ff74811cfbbf42e314a7fa754362e08bc5aece96daaf0712287f5248`。
- `batch-no-lead-n14a.json` SHA256 `b8fd72098cd4173943de966c695a6a06f97c8cb841e7eb5a35498679be164394`。
- `no-lead-n14a-final-receipt.json` SHA256 `107b1c2a5f9eeda16f559112f6fa3112c2c8635a54c248d329e67322dbcc2cb6`。
- `no-lead-n14a-offline-final-audit.json` SHA256 `de9b76abb5316d7b14ca787df1709cc5eae76c3b641701a251c8f2380b858872`。

独立脚本 `prepare-no-lead-n14a.py`、`begin-no-lead-n14a-search.py`、`read-no-lead-n14a.py`、`finalize-no-lead-n14a.py` 保留步骤；核账命令 `.runtime/verification/Scripts/python.exe -X utf8 .runtime/baichuan-ai-local/independent-enrichment-20261017/audit-no-lead-n14.py` 为首次冻结执行命令，产物使用x拒绝覆盖，不应重新运行真实查询。网页读取公网DNS检查不声称完整产品SSRF证明。
