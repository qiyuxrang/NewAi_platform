# AI-T12 N10：固定 40 家具体字段复查

执行时间：2026-10-18 03:02（北京时间）。冻结 selection `no_usable_retained_lead[200:240]` 实际 40 家，邻接 N9 `[160:200]` 互斥；selection SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

实际每家一次具体字段/所在地查询，共 40 次，10 组原始返回与企业 ID 关联保存。分段保存及逐企业 journal 持久化。实际 9 次正常 TLS GET，9 份正文、7 个主体；每家最多 2 页、无重试。7 个已有失败 host 或已读 URL 跳过，未因搜索可见而重试。原 HTML、正文、SHA、准确摘录与文字定位均在新私有目录保存。

准备 4 家 8 个原空字段：地址 4、城市 2、邮箱 2，全部候选版本 1。来源为企业目录及 2026-09-08 协会成员专页；官网 0、发证核验 0、证书升级 0。原非空电话保留。协会文章的个人联系人、协会页脚、招聘 HR 邮箱不采。政府公告表头明确为“属地人社部门投诉地址/投诉电话”，没有误填给该行企业；三图集团联系页缺完整独立主体，未将集团地址/网站转填子公司。历史地址有冲突的主体保留缺口。

固定 40 行当前版本和所选原值 RO 核对通过。`validate_batch` 在 SQL 新连接/网络禁止时实际 PASS。固定切片、40 查询绑定、相邻范围互斥、每企业请求上限、原件哈希离线核账 PASS。模型、业务写、服务与前端变更均 0。候选待根执行者唯一审核应用，不代表实际入库或全字段终态。

私有恢复文件位于 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

- `cohort-no-lead-n10.json` SHA256 `f5d4e149f1834a222088d7bb11ed40296500cca1e557edb1551857a605a84ae6`。
- `research-no-lead-n10.json` SHA256 `9f09dcb9a26ec799368cf3e739822b3ce776bf5f312c842e49a385854334da7d`。
- `batch-no-lead-n10.json` SHA256 `58e8ded55a5cc8dd5e84f9087514a459225e185baa4394ab177bb9ae31992472`。
- `no-lead-n10-final-receipt.json` SHA256 `fd7365a109f3034e82d016c3c65029efeabd374d28cf6ddaa268e2cb680e65c2`。
- `no-lead-n10-offline-final-audit.json` SHA256 `a26d83084d940c68bbdf7988ae605e6eb487bad7eb376bad38af90a05e6f1b6d`。

独立脚本 `prepare-no-lead-n10.py`、`begin-no-lead-n10-search.py`、`read-no-lead-n10.py`、`read-no-lead-n10-second.py`、`finalize-no-lead-n10.py` 留存实际步骤；冻结原件不应覆盖重跑。HTTP URL 离线选择和实际正常 TLS/DNS 公网检查不宣称为产品 SSRF 全面核验。
