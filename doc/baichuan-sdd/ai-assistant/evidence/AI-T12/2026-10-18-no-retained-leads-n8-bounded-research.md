# AI-T12 N8：固定无可用保留线索企业的有界复查

执行时间：2026-10-18 02:57（北京时间）。固定 selection `no_usable_retained_lead[140:160]`，20 家，与 N7 范围互斥。selection SHA256：`325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

实际完成 20 次具体字段与所在地检索，7 次正常 TLS 公开 GET、7 份可见正文；1 个已有失败 host 跳过，不重试。原 HTML、正文、准确摘录、定位与 SHA 均在私有新目录保存，搜索摘要不代替正文。

准备 6 家 8 个原空字段候选：地址 6、省份 1、邮箱 1。来源为企业目录、百科或行业资料，非工商或发证机构核验；官网候选 0、证书升级 0。原非空电话保留。集团网站、采购/招聘/平台联系排除；旧招聘资料与后续公告地址冲突未提议，另一个目录地址与历史旧址差异在候选定位中保留。

固定 20 家当前版本与所选原值只读复核通过。`validate_batch` 在禁止 SQL 新连接及网络条件下实际 PASS；固定 ID、20 条查询关联、相邻范围互斥、冻结文件哈希离线核账 PASS。模型调用、业务写入、前端改动、服务改动均 0。批次仅准备，根执行者唯一审核入库；不是全字段终态完成。

私有恢复入口（项目 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`）：

- `research-no-lead-n8.json` SHA256 `41f93c008fb53111a93ea8491a055f8345a12f53679894b6af77e993858a36fd`。
- `batch-no-lead-n8.json` SHA256 `7c2dbde70926cb7662ccffefdfbd4080d1070b4172e24041eecca553ef6adf19`。
- `no-lead-n8-final-receipt.json` SHA256 `63c4896000a9541498ab8e0d7bfce8c7d0e13d7ef19c07da61d9de64e8592a97`。
- `no-lead-n8-offline-final-audit.json` SHA256 `f85c23fc4fbbe6590e0d0cead0ed0ef6060190850a426fdf15d83ad2d3d134ae`。

可复查准备/执行命令记录在同目录 `prepare-no-lead-n8.py`、`begin-no-lead-n8-search.py`、`read-no-lead-n8.py`、`finalize-no-lead-n8.py`；已冻结文件和网络请求不得原样重跑覆盖。
