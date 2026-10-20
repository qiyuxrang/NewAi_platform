# AI-T12 N12B：固定 20 家有界具体字段复查

执行时间：2026-10-18 03:11（北京时间）。冻结 selection `no_usable_retained_lead[300:320]` 实际 20 家，N11 `[240:280]` 及 N12a/b 彼此互斥；selection SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

实际完成每家一次具体字段/所在地查询，共 20 次，5 组完整原始搜索返回与企业 ID 留存。实际 8 次正常 TLS GET，8 份正文、6 个主体；0 次失败、1 个既有失败 host/已读 URL 跳过，每家最多 2 页，0 重试。失败只留缺口，不以摘要代替正文。成功原 HTML/正文/SHA/准确摘录与定位均存新私有目录。

准备 4 家 7 个原空字段候选：{"address": 4, "city": 2, "province": 1}。候选版本全部 1，官网 0、证书升级 0、工商/发证核验 0。原非空电话及其他值保留。来源为企业目录、百科或行业合作渠道公开披露，未经独立登记核实，不代表资质满足。

厂家渠道表中的信易达全称与业务联系地址只支持该行地址/城市，不采个人销售手机或厂家总部联系，不将厂家站当目标官网。广电及正大招聘资料地址缺城市，未补写；“安康市首康建筑工程有限责任公司”与原表“安康市首康建筑有限责任公司”不同，未推断更名。锐声音视裸域名不猜协议，资质自述不升级。

固定 20 行当前版本/所选原值 RO 核对通过。`validate_batch` 在 SQL 新连接、DNS、socket 禁止条件下实际 PASS，三种拒绝探针逐项实际 PASS；固定切片、查询关联、范围互斥、请求上限及冻结文件哈希离线核账 PASS。模型、业务写入、前端或服务变更均 0。根执行者唯一审核应用，本单元候选不是实际入库或全字段终态交付。

私有恢复文件在 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

- `cohort-no-lead-n12b.json` SHA256 `4e960b43f33de19bb798c6c9501e354db44fb3065800aae2939446bafae36a1b`。
- `research-no-lead-n12b.json` SHA256 `a7620450193823935f16bf5634a34fe6337c1daa4f347785f6ac66692612e33e`。
- `batch-no-lead-n12b.json` SHA256 `10ed6470e5494ed42f3219a73a9f3629f381c1b652259d1e50a4ba1a72f306f5`。
- `no-lead-n12b-final-receipt.json` SHA256 `47b20863af44b73a8dd384edb9004b931276d20f0ad2748bacdb0de8f4841984`。
- `no-lead-n12b-offline-final-audit.json` SHA256 `cad835e98890500dde7a3a677c7ccf2fd99c0709181bb85505f3fe92f05677fd`。

脚本 `prepare-no-lead-n12b.py`、`begin-no-lead-n12b-search.py`、`read-no-lead-n12b.py`、`read-no-lead-n12b-second.py`、`finalize-no-lead-n12b.py` 保留步骤。冻结原件不覆盖、不原样重复请求；网页读取的公网 DNS 检查不声称为产品完整 SSRF 证明。
