# AI-T12 N12A：固定 20 家有界具体字段复查

执行时间：2026-10-18 03:11（北京时间）。冻结 selection `no_usable_retained_lead[280:300]` 实际 20 家，N11 `[240:280]` 及 N12a/b 彼此互斥；selection SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`。

实际完成每家一次具体字段/所在地查询，共 20 次，5 组完整原始搜索返回与企业 ID 留存。实际 4 次正常 TLS GET，3 份正文、2 个主体；1 次失败、2 个既有失败 host/已读 URL 跳过，每家最多 2 页，0 重试。失败只留缺口，不以摘要代替正文。成功原 HTML/正文/SHA/准确摘录与定位均存新私有目录。

准备 1 家 3 个原空字段候选：{"address": 1, "city": 1, "email": 1}。候选版本全部 1，官网 0、证书升级 0、工商/发证核验 0。原非空电话及其他值保留。来源为企业目录、百科或行业合作渠道公开披露，未经独立登记核实，不代表资质满足。

聚合源公司详情只有“汇鑫中心B座”，缺完整城市门牌，未补入；Dunjob单次请求超时后不重试，保存意图与实际错误；招聘个人/平台400联系排除。新纬度目录仅取目标完整企业块，不取相邻新秦巴或上海企业联系。

固定 20 行当前版本/所选原值 RO 核对通过。`validate_batch` 在 SQL 新连接、DNS、socket 禁止条件下实际 PASS，三种拒绝探针逐项实际 PASS；固定切片、查询关联、范围互斥、请求上限及冻结文件哈希离线核账 PASS。模型、业务写入、前端或服务变更均 0。根执行者唯一审核应用，本单元候选不是实际入库或全字段终态交付。

私有恢复文件在 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

- `cohort-no-lead-n12a.json` SHA256 `0841bb92da99f03e487e617c03c04aeda8dbe110c5efc5aab0931996378ecffe`。
- `research-no-lead-n12a.json` SHA256 `b5a884345b6877a1ed42368f334069cd320dadc4c64257bec7c6ac5771bfb4fa`。
- `batch-no-lead-n12a.json` SHA256 `50e95162b07ea866a997815dec3520c4a88684c05dda838e46e44cbbcfe31613`。
- `no-lead-n12a-final-receipt.json` SHA256 `e29d1ecd77974b6b5355b18306138094d8839b2e387fd16c45ef1e30a1691f35`。
- `no-lead-n12a-offline-final-audit.json` SHA256 `922dd52d650c9a3666e09508e31abaee118ead29e5466b3278938920ce943aef`。

脚本 `prepare-no-lead-n12a.py`、`begin-no-lead-n12a-search.py`、`read-no-lead-n12a.py`、`read-no-lead-n12a-second.py`、`finalize-no-lead-n12a.py` 保留步骤。冻结原件不覆盖、不原样重复请求；网页读取的公网 DNS 检查不声称为产品完整 SSRF 证明。
