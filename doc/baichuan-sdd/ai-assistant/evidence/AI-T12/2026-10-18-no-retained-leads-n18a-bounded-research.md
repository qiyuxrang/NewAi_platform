# AI-T12 N18A：固定20家有界具体字段复查

冻结时间：2026-10-18 03:39:27（北京时间）。冻结 selection `no_usable_retained_lead[520:540]` 实际20家，与N17 `[480:520]`、N18另一20家互斥。selection SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

每家一次具体字段/所在地查询，共20次，5组完整搜索返回及ID/意图已存。实际7次公开GET（HTTPS正常TLS验证、HTTP保留未加密），5份非空正文、4个主体；空正文0份，失败2次，旧失败host/已读URL跳过1个，0重试，每家最多2GET。搜索片段、空壳、相近主体不当正文事实。

准备3家8个原空字段候选：{"address": 3, "city": 3, "website": 1, "email": 1}，版本全部1。利源昌、长裕为完整主体公司地址公开目录；万禾为显式HTTP官网根页及可见同源联系页完整全称版权与业务联系，官网不升级HTTPS。悦泰总部与项目部混写不采；银兴摘要楼层冲突/旧失败不重试。

所有来源是公开披露候选，未提升为工商或发证核验；官网提议1、证书提议0。原非空值保留。完整原HTML/可见正文、SHA、精确摘录及定位留私有目录。20行当前版本/原值RO核对通过，随后SQL/DNS/socket拒绝条件下真实 `validate_batch` PASS，三个拒绝探针PASS；固定切片/互斥/查询绑定/请求上限/31个冻结原件hash离线核账PASS。模型、业务写、前端或服务变更均0。根执行者唯一审核应用，候选不是入库或全部12字段终态。

私有恢复目录 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

- `cohort-no-lead-n18a.json` SHA256 `66207deca463cba125cad5e2d241a0d0df083a4a4b54edb1c9dbb93df831e943`。
- `research-no-lead-n18a.json` SHA256 `0f233ea89617a2a0c1023c4f51b4858cd30c136ea54398be10cea32b2096ad96`。
- `batch-no-lead-n18a.json` SHA256 `4fc10a3a21f780118daa0337ac885013a3e335fe92bc1d91729892a5eb48e31b`。
- `no-lead-n18a-final-receipt.json` SHA256 `397111c1d06d10d7518dcd1494f9ade965f7f5c09333e26f4ad09654697cb2fe`。
- `no-lead-n18a-offline-final-audit.json` SHA256 `ac274e072a173a47372e07baa89891805fecad36e5ecb00f64a8dc4792b2ad62`。

独立脚本 `prepare-no-lead-n18a.py`、`begin-no-lead-n18a-search.py`、`read-no-lead-n18a.py`、`finalize-no-lead-n18a.py` 保留步骤；核账命令 `.runtime/verification/Scripts/python.exe -X utf8 .runtime/baichuan-ai-local/independent-enrichment-20261017/audit-no-lead-n18.py` 为首次冻结执行命令，产物使用x拒绝覆盖，不应重新运行真实查询。网页读取公网DNS检查不声称完整产品SSRF证明。
