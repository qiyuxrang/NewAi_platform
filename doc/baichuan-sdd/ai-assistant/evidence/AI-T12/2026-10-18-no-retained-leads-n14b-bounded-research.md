# AI-T12 N14B：固定20家有界具体字段复查

冻结时间：2026-10-18 03:20:52（北京时间）。冻结 selection `no_usable_retained_lead[380:400]` 实际20家，与N13 `[320:360]`、N14另一20家互斥。selection SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

每家一次具体字段/所在地查询，共20次，5组完整搜索返回及ID/意图已存。实际9次正常TLS GET，9份非空正文、7个主体；空正文0份，失败0次，旧失败host/已读URL跳过1个，0重试，每家最多2GET。搜索片段、空壳、相近主体不当正文事实。

准备6家8个原空字段候选：{"address": 6, "city": 1, "province": 1}，版本全部1。斯克达只采用2025学院公司介绍明确联系地址，工作厂区另列，HR手机/邮箱不采；中石、海讯、榆林智能、信越达、核音智言取完整主体的公开公司地址/显式省市。宇地历史原件为访问拦截，本轮跳过；九索有限公司与股份有限公司不擅自归并，有色集团根站不赋独立目标。

所有来源是公开披露候选，未提升为工商或发证核验；官网提议0、证书提议0。原非空值保留。完整原HTML/可见正文、SHA、精确摘录及定位留私有目录。20行当前版本/原值RO核对通过，随后SQL/DNS/socket拒绝条件下真实 `validate_batch` PASS，三个拒绝探针PASS；固定切片/互斥/查询绑定/请求上限/41个冻结原件hash离线核账PASS。模型、业务写、前端或服务变更均0。根执行者唯一审核应用，候选不是入库或全部12字段终态。

私有恢复目录 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

- `cohort-no-lead-n14b.json` SHA256 `8be7af72747359205e6823d2f24c57ffa39efc92156dcbb87106d88b8fdc428d`。
- `research-no-lead-n14b.json` SHA256 `9a79170a1daa4c0af94a1eac3cbb6da469502610122b7070fa13b1f7b3592506`。
- `batch-no-lead-n14b.json` SHA256 `365e08db48feb8d41024a5aa2f7fe90c2c4238f79cab55caf312ca424b1b17e4`。
- `no-lead-n14b-final-receipt.json` SHA256 `6c7ca657d9b58e3c6efa2a915452efe5f77835391123db05b39df95a1eaeb9e7`。
- `no-lead-n14b-offline-final-audit.json` SHA256 `3b542df98084d8972286f241d63097d1a931d0b4a8a7ae87cff90e9a4b5b207c`。

独立脚本 `prepare-no-lead-n14b.py`、`begin-no-lead-n14b-search.py`、`read-no-lead-n14b.py`、`finalize-no-lead-n14b.py` 保留步骤；核账命令 `.runtime/verification/Scripts/python.exe -X utf8 .runtime/baichuan-ai-local/independent-enrichment-20261017/audit-no-lead-n14.py` 为首次冻结执行命令，产物使用x拒绝覆盖，不应重新运行真实查询。网页读取公网DNS检查不声称完整产品SSRF证明。
