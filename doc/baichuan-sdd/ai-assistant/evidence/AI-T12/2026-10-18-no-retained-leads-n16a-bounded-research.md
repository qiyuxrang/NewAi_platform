# AI-T12 N16A：固定20家有界具体字段复查

冻结时间：2026-10-18 03:29:35（北京时间）。冻结 selection `no_usable_retained_lead[440:460]` 实际20家，与N15 `[400:440]`、N16另一20家互斥。selection SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

每家一次具体字段/所在地查询，共20次，5组完整搜索返回及ID/意图已存。实际9次正常TLS GET，8份非空正文、7个主体；空正文0份，失败1次，旧失败host/已读URL跳过2个，0重试，每家最多2GET。搜索片段、空壳、相近主体不当正文事实。

准备6家13个原空字段候选：{"address": 6, "city": 4, "email": 3}，版本全部1。群翔、煤亮子、银江、青鸟、绿创和西热控制均为完整主体公开公司资料；公司邮箱及地址按准确摘录提议。原非空电话不同不覆盖。沣西协会介绍母子公司联系归属有歧义未采，奥翔集团旧失败不重试，未将集团根站赋独立公司。

所有来源是公开披露候选，未提升为工商或发证核验；官网提议0、证书提议0。原非空值保留。完整原HTML/可见正文、SHA、精确摘录及定位留私有目录。20行当前版本/原值RO核对通过，随后SQL/DNS/socket拒绝条件下真实 `validate_batch` PASS，三个拒绝探针PASS；固定切片/互斥/查询绑定/请求上限/39个冻结原件hash离线核账PASS。模型、业务写、前端或服务变更均0。根执行者唯一审核应用，候选不是入库或全部12字段终态。

私有恢复目录 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

- `cohort-no-lead-n16a.json` SHA256 `1768c291873d9b5fc73884ddbceceb3dcfdb9de099bf4b4a32e2f4d364fd4cb8`。
- `research-no-lead-n16a.json` SHA256 `ca41f439387655668ad19d6e95e983432a33fc54bce3fc80bc9baad765851f5c`。
- `batch-no-lead-n16a.json` SHA256 `f1a2bf2bb436e050cffc5df26ba2b2c027c77705844d999c19adb084dbb41fbd`。
- `no-lead-n16a-final-receipt.json` SHA256 `585cde9a306f3d81090385d195e8b4dfb727d894f2daed606f510d79352a4a61`。
- `no-lead-n16a-offline-final-audit.json` SHA256 `50fa53ac976b14c982cb7475c00d334612d740b76574391a938f1689358c1115`。

独立脚本 `prepare-no-lead-n16a.py`、`begin-no-lead-n16a-search.py`、`read-no-lead-n16a.py`、`finalize-no-lead-n16a.py` 保留步骤；核账命令 `.runtime/verification/Scripts/python.exe -X utf8 .runtime/baichuan-ai-local/independent-enrichment-20261017/audit-no-lead-n16.py` 为首次冻结执行命令，产物使用x拒绝覆盖，不应重新运行真实查询。网页读取公网DNS检查不声称完整产品SSRF证明。
