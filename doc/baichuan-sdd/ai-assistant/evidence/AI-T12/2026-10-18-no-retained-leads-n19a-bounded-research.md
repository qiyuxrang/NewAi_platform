# AI-T12 N19A：固定16家有界具体字段复查

冻结时间：2026-10-18 03:44:03（北京时间）。冻结 selection `no_usable_retained_lead[560:576]` 实际16家，与N18 `[520:560]`、N19另一16家互斥。selection SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

每家一次具体字段/所在地查询，共16次，4组完整搜索返回及ID/意图已存。实际6次公开GET（HTTPS正常TLS验证、HTTP保留未加密），4份非空正文、4个主体；空正文0份，失败2次，旧失败host/已读URL跳过1个，0重试，每家最多2GET。搜索片段、空壳、相近主体不当正文事实。

准备3家3个原空字段候选：{"address": 3}，版本全部1。顺和兴、恒巨、万飞各一地址候选；恒巨地址只保留独立公司地址栏实际字符串，未附猜测城市。顺和兴证书标有效却2025到期不作核实；安源简介无地址/平台邮箱不采，中民投TLS主机名错误不降级。

所有来源是公开披露候选，未提升为工商或发证核验；官网提议0、证书提议0。原非空值保留。完整原HTML/可见正文、SHA、精确摘录及定位留私有目录。16行当前版本/原值RO核对通过，随后SQL/DNS/socket拒绝条件下真实 `validate_batch` PASS，三个拒绝探针PASS；固定切片/互斥/查询绑定/请求上限/26个冻结原件hash离线核账PASS。模型、业务写、前端或服务变更均0。根执行者唯一审核应用，候选不是入库或全部12字段终态。

私有恢复目录 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

- `cohort-no-lead-n19a.json` SHA256 `e5b991c992225fb2b14769bf6fc9a157dfbdd0844120010b400076574c77e087`。
- `research-no-lead-n19a.json` SHA256 `956481031c133c9b95847bb35073c4596b6eced22bdbe23b0369a7b24236addd`。
- `batch-no-lead-n19a.json` SHA256 `434d65111f42feaf176aedb0b7ee6e9449bb0422e3b15f7767608e14fca5bbba`。
- `no-lead-n19a-final-receipt.json` SHA256 `76236fc3123f3d91ec92eaf1846e0ba77dfd08019d6062dd871f9146cc8e8bd4`。
- `no-lead-n19a-offline-final-audit.json` SHA256 `38a4592a9aea0d503145f4d799f163bd54ec281a37e18aeeade68b06e4567e5d`。

独立脚本 `prepare-no-lead-n19a.py`、`begin-no-lead-n19a-search.py`、`read-no-lead-n19a.py`、`finalize-no-lead-n19a.py` 保留步骤；核账命令 `.runtime/verification/Scripts/python.exe -X utf8 .runtime/baichuan-ai-local/independent-enrichment-20261017/audit-no-lead-n19.py` 为首次冻结执行命令，产物使用x拒绝覆盖，不应重新运行真实查询。网页读取公网DNS检查不声称完整产品SSRF证明。
