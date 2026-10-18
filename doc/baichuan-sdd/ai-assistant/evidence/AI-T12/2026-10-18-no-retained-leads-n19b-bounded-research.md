# AI-T12 N19B：固定16家有界具体字段复查

冻结时间：2026-10-18 03:44:05（北京时间）。冻结 selection `no_usable_retained_lead[576:592]` 实际16家，与N18 `[520:560]`、N19另一16家互斥。selection SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

每家一次具体字段/所在地查询，共16次，4组完整搜索返回及ID/意图已存。实际4次公开GET（HTTPS正常TLS验证、HTTP保留未加密），4份非空正文、4个主体；空正文0份，失败0次，旧失败host/已读URL跳过1个，0重试，每家最多2GET。搜索片段、空壳、相近主体不当正文事实。

准备4家6个原空字段候选：{"address": 4, "province": 1, "city": 1}，版本全部1。华山智旅地址、承泰地址/省、中奥数智地址、寰华地址/城市；均有实际完整主体公开原文和准确定位。原非空值保留，集团/旅游平台/招聘个人/平台footer不混主体；建设通公司及人员资质不升级为发证核实。

所有来源是公开披露候选，未提升为工商或发证核验；官网提议0、证书提议0。原非空值保留。完整原HTML/可见正文、SHA、精确摘录及定位留私有目录。16行当前版本/原值RO核对通过，随后SQL/DNS/socket拒绝条件下真实 `validate_batch` PASS，三个拒绝探针PASS；固定切片/互斥/查询绑定/请求上限/22个冻结原件hash离线核账PASS。模型、业务写、前端或服务变更均0。根执行者唯一审核应用，候选不是入库或全部12字段终态。

私有恢复目录 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

- `cohort-no-lead-n19b.json` SHA256 `9be52ce4b5cf185c259aa2a3e484f4d4119a4af9e3b0642bdfd29cbf53a262cb`。
- `research-no-lead-n19b.json` SHA256 `b6863d692829dcfb861d4d248b2ba9451eb7dbb2d24e5722c6b07f931c7400ed`。
- `batch-no-lead-n19b.json` SHA256 `86e7d4136c6cf57d7c0990fc3a91469ea4ae1bfdcfe398a9d8471d2ad63d4017`。
- `no-lead-n19b-final-receipt.json` SHA256 `77451b7887f13e7c7b6d72d6e30440bfc5208981373db2dc799e23fd3d169564`。
- `no-lead-n19b-offline-final-audit.json` SHA256 `565447e0d2acb09af4e7d4859b95da68e762fcfb5f3bf1b377ee2b1061dd7db3`。

独立脚本 `prepare-no-lead-n19b.py`、`begin-no-lead-n19b-search.py`、`read-no-lead-n19b.py`、`finalize-no-lead-n19b.py` 保留步骤；核账命令 `.runtime/verification/Scripts/python.exe -X utf8 .runtime/baichuan-ai-local/independent-enrichment-20261017/audit-no-lead-n19.py` 为首次冻结执行命令，产物使用x拒绝覆盖，不应重新运行真实查询。网页读取公网DNS检查不声称完整产品SSRF证明。
