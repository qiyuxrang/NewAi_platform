# AI-T12 N18B：固定20家有界具体字段复查

冻结时间：2026-10-18 03:39:28（北京时间）。冻结 selection `no_usable_retained_lead[540:560]` 实际20家，与N17 `[480:520]`、N18另一20家互斥。selection SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

每家一次具体字段/所在地查询，共20次，5组完整搜索返回及ID/意图已存。实际3次公开GET（HTTPS正常TLS验证、HTTP保留未加密），3份非空正文、2个主体；空正文0份，失败0次，旧失败host/已读URL跳过3个，0重试，每家最多2GET。搜索片段、空壳、相近主体不当正文事实。

准备2家4个原空字段候选：{"address": 2, "city": 1, "email": 1}，版本全部1。中能瑞通仅CMMI中文网完整主体注册地址目录候选，不作证书核验；其所列网址实际版权为北京主体，未赋西安企业官网/集团邮箱。赢海目录公司地址/邮箱可采，原非空电话不同保留。

所有来源是公开披露候选，未提升为工商或发证核验；官网提议0、证书提议0。原非空值保留。完整原HTML/可见正文、SHA、精确摘录及定位留私有目录。20行当前版本/原值RO核对通过，随后SQL/DNS/socket拒绝条件下真实 `validate_batch` PASS，三个拒绝探针PASS；固定切片/互斥/查询绑定/请求上限/23个冻结原件hash离线核账PASS。模型、业务写、前端或服务变更均0。根执行者唯一审核应用，候选不是入库或全部12字段终态。

私有恢复目录 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

- `cohort-no-lead-n18b.json` SHA256 `e3be51c613aadbef0772bcaaaa9b5849553bcdb5e63ddd669ba016f74844560d`。
- `research-no-lead-n18b.json` SHA256 `637563a87c729bdb3768fd5da09c6caf1fe6cd5c8ff6fedbf49840a20ab5dd9c`。
- `batch-no-lead-n18b.json` SHA256 `aa2f0961efaecfbfc27c00bd5ca39313776b4baadc1572e1048f8941d44b1cd1`。
- `no-lead-n18b-final-receipt.json` SHA256 `391def8a3b7278c2c8b91463f7d9f2c393f50c0c15ceb84b587c83a8a34e74cd`。
- `no-lead-n18b-offline-final-audit.json` SHA256 `53bf63688f49c30247e63ac9fcf8751575af693b99c793f99f4e4b2d540d6dd6`。

独立脚本 `prepare-no-lead-n18b.py`、`begin-no-lead-n18b-search.py`、`read-no-lead-n18b.py`、`finalize-no-lead-n18b.py` 保留步骤；核账命令 `.runtime/verification/Scripts/python.exe -X utf8 .runtime/baichuan-ai-local/independent-enrichment-20261017/audit-no-lead-n18.py` 为首次冻结执行命令，产物使用x拒绝覆盖，不应重新运行真实查询。网页读取公网DNS检查不声称完整产品SSRF证明。
