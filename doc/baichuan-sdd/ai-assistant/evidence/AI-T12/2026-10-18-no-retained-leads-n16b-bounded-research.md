# AI-T12 N16B：固定20家有界具体字段复查

冻结时间：2026-10-18 03:29:36（北京时间）。冻结 selection `no_usable_retained_lead[460:480]` 实际20家，与N15 `[400:440]`、N16另一20家互斥。selection SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

每家一次具体字段/所在地查询，共20次，5组完整搜索返回及ID/意图已存。实际8次正常TLS GET，6份非空正文、5个主体；空正文0份，失败2次，旧失败host/已读URL跳过3个，0重试，每家最多2GET。搜索片段、空壳、相近主体不当正文事实。

准备5家11个原空字段候选：{"address": 5, "city": 4, "email": 2}，版本全部1。中联华科、峰创、太极航空、勇捷及长安计算各有完整主体公司字段。峰创前方简介明确AI生成，摘录从独立工商名称及公司地址栏开始，未据AI文案赋任何证书。长安计算图文旧更新时间2022-08-30及可能陈旧提示完整保留，仅待根审候选。TLS主机名错误/403未重试，博亚及捷润旧失败不重复；官网未据片段赋值。

所有来源是公开披露候选，未提升为工商或发证核验；官网提议0、证书提议0。原非空值保留。完整原HTML/可见正文、SHA、精确摘录及定位留私有目录。20行当前版本/原值RO核对通过，随后SQL/DNS/socket拒绝条件下真实 `validate_batch` PASS，三个拒绝探针PASS；固定切片/互斥/查询绑定/请求上限/34个冻结原件hash离线核账PASS。模型、业务写、前端或服务变更均0。根执行者唯一审核应用，候选不是入库或全部12字段终态。

私有恢复目录 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

- `cohort-no-lead-n16b.json` SHA256 `154a389dcadcc46d3493941233d94ef316753d34cddda8dbf1c95fe7a8e03550`。
- `research-no-lead-n16b.json` SHA256 `d83095d3fba57759b49101021a24bf4f36712f7d39b82b1e05c4fe3d16193fe1`。
- `batch-no-lead-n16b.json` SHA256 `3762d0090c33da743f96be275e458da81b1e9a3ca7910240745ee85fad504dbe`。
- `no-lead-n16b-final-receipt.json` SHA256 `d03409871d5921c8b87377557bf6e95ba6e429effb9d6a4f3d9d8c08f6b4e8dd`。
- `no-lead-n16b-offline-final-audit.json` SHA256 `9cf4ff1d32bf084194eab492fb21423a80ca4e3c41ec184ab5d4a637700c9050`。

独立脚本 `prepare-no-lead-n16b.py`、`begin-no-lead-n16b-search.py`、`read-no-lead-n16b.py`、`finalize-no-lead-n16b.py` 保留步骤；核账命令 `.runtime/verification/Scripts/python.exe -X utf8 .runtime/baichuan-ai-local/independent-enrichment-20261017/audit-no-lead-n16.py` 为首次冻结执行命令，产物使用x拒绝覆盖，不应重新运行真实查询。网页读取公网DNS检查不声称完整产品SSRF证明。
