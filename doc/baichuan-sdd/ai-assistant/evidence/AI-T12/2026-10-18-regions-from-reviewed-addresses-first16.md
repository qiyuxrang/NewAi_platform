# AI-T12：从已应用联系地址离线核对地区，首16家

本单元于2026-10-18 05:34:38（北京时间）冻结。只读核查实际本地库，当前地址必须精确等于已应用 address 修订的新值，且省或市仍为空；符合条件20家，本单元固定前16家，余4家当时尚未执行，另单元处理。

16家均已核对原批次文件 SHA、对应企业、原地址断言、完整正文 SHA、摘录及定位。只有3家原地址含完整字面“西安市”，形成3个 city 补空候选：中煤航测遥感集团有限公司（版本3）、数邦电力科技有限公司（版本4）、西安晨舟电子科技有限公司（版本4）。3个候选的原始 HTML hash 另行核对通过，原读取时间、来源类型及正文保持；省份非空及原地址不修改。这是公司办公/联系地点，不是工商注册地区核实。

其余13家保留未知：“西安”简称、西咸新区、区县、公司名称不能推导完整市名或省名。未生成无依据的字段。

候选使用当前 reviewed_enrichment 格式，实际 `validate_batch` 通过；验证进程拒绝 SQL、socket 和 DNS，三类调用尝试均0。网络、搜索、模型及业务写入均0。实际入库由根执行者独立审阅和 CAS 完成，此证据不表示已应用。

私有目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/region-from-reviewed-addresses-20261018-0532/`。

| 冻结文件 | SHA-256 |
| --- | --- |
| cohort.json | ca6657a5692be90a1108444c19f03f2e0064f89b4a1ef97695bbc1ef9d37d4ed |
| batch-region-from-reviewed-addresses.json | aae5441d3b44e8cb3007e8a25c632219b9775943a0dec5c60ec9722f0e7e28b1 |
| address-source-binding-proof.json | 6cf9627b261727c5e26aff9be916cde5b4f067663ff77deda0a3f973cc82ee70 |
| journal-final.json | aaba3a95c063119fd5983156dd80bbabc329a96b48a8a1f01283411b0be4ccee |
| file-manifest.json | 0090ac9f96b4a495a8146a6aa7c8d35b9b8a254e1d8a3685ea1b042d6aec883f |
| final-receipt.json | 3fb9321dbf68eb769bbad35c551494d05791ad69014d317b755d443e0c45e698 |

可重复离线规则及实际执行脚本保存在同目录 `prepare-batch.py`、`validate-offline.py`、`freeze-final.py`；脚本采用排他创建，重跑应使用新目录，不覆盖冻结产物。未改核心代码、页面、服务配置或共享任务状态。
