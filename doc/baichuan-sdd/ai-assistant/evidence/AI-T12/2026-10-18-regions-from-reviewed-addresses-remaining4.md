# AI-T12：原20家联系地址地区核对，余4家

2026-10-18 05:39:34（北京时间）冻结。短连接 SQLite `mode=ro` 取样并关闭，排除首16家后，原集合剩余正好4家；未扩大范围。随后原批次和正文核对、候选校验、冻结均拒绝 SQL/socket/DNS。

| 企业及冻结版本 | 结论 |
| --- | --- |
| 西安元智系统技术有限责任公司，3 | 原已应用地址“陕西省西安市高新区锦业路69号创业研发园E座4F”含完整“西安市”，仅准备 city 补空 |
| 陕西化建工程有限责任公司，3 | “陕西杨凌示范区新桥路2号”无完整城市名称，未知 |
| 陕西恒巨软件科技有限公司，2 | 地址只有高新区和道路，无完整城市名称，未知 |
| 陕西益利德软件科技有限公司，3 | 西咸新区/沣西新城不推断地级市，未知 |

4家均实际核对当前地址与已应用修订、原字段断言、原批次 SHA、完整正文 SHA、摘录及定位。元智原始 HTML SHA 实测匹配 `13c388236961b36de094bdeb1a26ab13846d3f4c891c798f706233ddc27ba2f1`；新来源明确 `corporate`，依据是原已应用同源官网断言及原完整公司正文。旧证据未显式记录来源类型，保持原件不变；不升级工商身份或发证权威。

原来源时间、正文及定位保持；原地址、省份均不修改。城市是办公/联系地点字面值，不是工商注册地区核实。仅1家1字段候选，实际 `validate_batch` PASS，SQL/socket/DNS 调用尝试均0；网络、搜索、模型和业务写入均0。实际应用由根执行者独立审核及 CAS 完成。

首16与余4交集0、并集20，20家均完成此项地址来源核对：总计4个 city 候选、16家无可安全派生字段。不代表全部12字段研究终态。

私有目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/region-from-reviewed-addresses-remaining4-20261018-0536/`。

| 文件 | SHA-256 |
| --- | --- |
| cohort.json | 8d39aee984293f01cf9b2f5b82efab8b95ea03fdfd77169e83232c07d91e19bf |
| batch-region-from-reviewed-addresses-remaining4.json | f6f11804c669c55a116130c9f0af8ae80510a7039ac3ca6805b4d929929d8f1f |
| address-source-binding-proof.json | 2cdf1c71f50ecbdb893fe430561c8cce1de53396038b914dce6f74feb334aebe |
| journal-final.json | 7eec543e9fb21de560010b0a7c8a33b8dc65246159bd83ca3aec2b11af5b1cfb |
| file-manifest.json | 754e2fd37837aa8c7fa193cc3926e3f109a2a1bfe80c132ace1510801a2f936a |
| final-receipt.json | 927b920bfd7c7ed657091bdf5925b72edbbfa338f1ae321d39f79241ed82897b |

可复核脚本：同目录 `readonly-cohort.py`、`prepare-offline.py`、`validate-offline.py`、`freeze-final.py`。采用排他创建，冻结产物未覆盖；未改核心代码、页面、服务或共享任务状态。
