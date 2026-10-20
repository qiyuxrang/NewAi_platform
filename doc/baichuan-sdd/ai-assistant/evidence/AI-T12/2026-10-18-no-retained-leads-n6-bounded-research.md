# AI-T12 N6：固定无可用留存线索分片研究

执行时间：2026-10-18 02:45–02:50（北京时间）。仅研究、候选准备和离线校验；未执行入库。GM验收安静窗口内，业务库只读，无服务或配置操作。

固定选择文件 `selection-next-after-w12.json` SHA256 `325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68`，实际 `no_usable_retained_lead` 长592，本次严格 `[100:120]` 共20个唯一ID，与N5 `[80:100]` 无交集。启动和冻结时使用 SQLite `mode=ro`、`query_only` 读取当前20行ID/名称/version/空字段，选定字段无变化，连接及时关闭。

## 实际执行与边界

每家1次新所在地/官网/联系电话具体查询，共20次；五组实际搜索完整字符串及意图文件保存。搜索摘要不作为正文或写入依据。既有失败host/已完成相同URL在请求前排除，未猜域名或重复全称初搜。

4次公开固定URL GET：2份正常TLS非空正文，2次失败分别为403与302；302未跟随，均未重试。每公司实际最多1次GET，最多2并发，每请求12秒/2MiB上限。新搜索发现的企业官网域名已有 `research-j.json` 精确URL `URLError` 记录，因此跳过，不因摘要全名/电话看似匹配即赋官网。

准备2家3个原空字段候选（地址2、城市1），所有候选预期version1：

- 一份政府公共资源交易中心主体资料页明确企业完整名称及“法人机构地址”，作为 `publication_kind=government` 公开披露候选；页面未显示资料更新日期，不宣称工商登记核验或最新办公地址。旧招聘和采购摘要另有办公地址线索，完整保留，既有电话不覆盖。
- 一份公开企业目录的地址段与企业简介明确目标及“西安市”，作为 `publication_kind=directory` 地址/城市候选。曾用名只保留来源自述，不据此合并其他企业；平台400热线不归目标。

没有可靠新官网/通用电话候选。集团子公司介绍、集团全国主页、分公司旧采购、医院/代理联系人、不同全名企业、招聘咨询、应用商店开发者和标准起草名单不等于目标当前通用联系来源。ISO历史暂停线索未改变七类资质或当前证书状态；未知不判满足。

`validate_batch` 实际PASS，校验阶段SQL/socket连接deny。离线复核20份原件/正文/意图/搜索文件hash、20查询与固定ID绑定、N5互斥全部PASS。模型调用、业务写、前端/服务/配置/共享状态变更均0。两家公司读到正文不等于20家或12字段研究终态；其余18家明确保存缺口。

## 冻结文件

私有文件均相对 `.runtime/baichuan-ai-local/independent-enrichment-20261017/`：

| 文件 | SHA256 |
| --- | --- |
| `cohort-no-lead-n6.json` | `a3d3dea2f547cadf639d0707250386df6f3d9faa237fbc15641bc11dfe02cd38` |
| `research-no-lead-n6.json` | `65aed595e65650698571b9881bbcc05c7de8702ff3bc8b8451dbd4a08d10f5e0` |
| `batch-no-lead-n6.json` | `55c604d525267af81919526ed6245b014df7056b59d315bd6cada1452bc39a3d` |
| `no-lead-n6-final-receipt.json` | `e9ff38193c7b99d7288a5d39ca24170689710d7ec5d98d8ae620f7efcc3e5931` |
| `no-lead-n6-offline-final-audit.json` | `aafd06131b9bbc4a1da1a742c4a521bf5859fd59db3c5aec3e8496fbd7578fbb` |

入口：私有 `prepare-no-lead-n6.py`、`begin-no-lead-n6-search.py`、`read-no-lead-n6.py`、`finalize-no-lead-n6.py`；既有 `.runtime/verification/Scripts/python.exe -X utf8` 与可见HTML文本解析器，无新增依赖或外部实现。原搜索在 `no-lead-n6-search/`，HTML/正文/每URL意图在 `no-lead-n6-raw/`；HTTP失败只记录错误与意图，未声称有失败页完整HTML。冻结字节不可覆盖或重复请求。恢复先核SHA/逐家来源与缺口，再由根执行者审查候选及当前版本后走受控维护；本文件不宣称实际应用，主检查点与全库覆盖由根统一维护。
