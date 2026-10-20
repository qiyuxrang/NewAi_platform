# AI-T12 N4：固定无可用留存线索分片研究

执行时间：2026-10-18 02:36–02:40（北京时间）。仅研究、准备及校验；未入库，未完成全字段终态。

固定选择文件 `selection-next-after-w12.json` SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`，实际 `no_usable_retained_lead` 共592项。本次严格 `[60:80]` 20个唯一ID，与N3 `[40:60]` 无交集。启动及冻结时分别通过SQLite `mode=ro`/`query_only` 读取当前ID/名称/version/空字段，选定20行冻结前保持一致；不接入远程库。

## 实际结果

20次新具体字段/所在地查询（每企业1次），原搜索完整字符串与5组意图文件保留。结果中的搜索摘要不算实际正文。既有失败host/已完成相同URL执行前排除；采购聚合失败域没有重试，不猜官网，不扩搜索预算。

7次正常TLS公开固定URL GET，分属5家公司，7份非空可见正文均含对应完整法定全称。两家公司第二页来自第一页面可见的目标公司资料链接。每公司最多2页、每请求12秒/2MiB、并发2、0自动重试或跳转；请求/原HTML/解析正文及SHA全部留存。

准备3家公司5个原空字段，均明确 `publication_kind=directory`：地址3、省份2。仅使用公司简介注册地址/企业黄页详细地址/2026-09-23会员介绍注册地址的原文字面值及精确文本定位；没有给目录赋予工商/发证权威。来源中2025-10-31更新的公司简介只提供当时披露，并非独立确认其2026地址未变；有边界的公开披露候选由根审核决定。无网站或电话候选，既有电话/城市/省份等非空值全部保留。

平台400热线、英才协会页脚B座地址/电话/邮箱、岗位HR、其他公司近名、采购方联系不归目标。2022合作公告和2023合同旧地址不冒充当前；公司资料只有街道门牌或园区名的两家，本批保守留缺口，不从招聘工作地/面包屑拼接完整地址或城市。招聘页徽标/自述资质未升级七类资质或已确认匹配。

`validate_batch` 实际PASS；校验时SQL及socket连接均被deny。离线核账35份原件/正文/搜索收据hash、20查询和固定ID逐项对应、N3互斥全部PASS。模型调用、业务写、前端/服务/全局配置变更0。其余17家没有安全候选；5家正文读取不是20家或12字段研究完成，工商/证书核实没有增加。

## 冻结文件及恢复点

私有文件均相对 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

| 文件 | SHA256 |
| --- | --- |
| `cohort-no-lead-n4.json` | `1e5953153630a4313237382ad5a35cedb87a1b97b641f0d7af399fb271885862` |
| `research-no-lead-n4.json` | `4344dabc696ccc4794a5b6f61073633ac642b5a79a7c28bd4f25ab5a7bf82966` |
| `batch-no-lead-n4.json` | `b0c85b4960a6da2857ff4625a19ede5a7b162ce1c8229d40327ed03988674dd8` |
| `no-lead-n4-final-receipt.json` | `3c0685ae30bd82a068f7cd3c526175db523cdf3fb737ec0e8b2c3317a3e90203` |
| `no-lead-n4-offline-final-audit.json` | `6990c7f31017c422ff76b5e5eeabd8f02e174edafd1972061ab6411ac9237a5b` |

有界研究入口为私有 `prepare-no-lead-n4.py`、`begin-no-lead-n4-search.py`、`read-no-lead-n4.py`、`read-no-lead-n4-second.py`、`finalize-no-lead-n4.py`。使用既有 `.runtime/verification/Scripts/python.exe -X utf8` 和现有HTML解析器，无新增外部实现或依赖。查询原收据在 `no-lead-n4-search/`，实际HTML/正文/逐URL意图在 `no-lead-n4-raw/`。冻结原件不可覆盖，不重复联网；恢复先核hash和逐家缺口，根审查候选及当前版本后走已有受控维护。共享任务/检查点/覆盖索引由根统一更新。
