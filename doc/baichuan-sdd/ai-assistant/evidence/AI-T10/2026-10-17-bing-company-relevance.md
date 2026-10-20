# AI-T10：首家真实试查的RSS相关性失败

2026-10-17。根代理授权只读实际pilot来源记录，并最多2次对同一已公开企业名做普通公开对照。未调用模型、正文抓取、绕过挑战或搜索轮换，未改数据库/事实/共享搜索代码。

## 实际证据

新增可复查诊断 `scripts/baichuan/diagnose_bing_relevance.py`。实际命令为 `.runtime/company-test/python/Scripts/python.exe scripts/baichuan/diagnose_bing_relevance.py --two-public-comparisons`；仅执行一次。实际企业库通过SQLite `mode=ro` 与 `PRAGMA query_only=ON` 读取，随后独立临时Django配置禁止SQL。仅固定 `https://www.bing.com/search`、现有适配器标准TLS及本机无凭据代理、NoRedirect；每请求8秒/262144B限制，2次后结束。

实际清单ID为 `3a73d8fe-9b2e-58d1-8507-7d73b835fd61`，总数1283。首家 `search_index` 重建“公开企业全称 + 官网 联系方式 公开资质”的SHA256为 `e6b8e815f5a2f8fe6be3c349624a4ca66ece39ca167fcf445b6db00707f7117e`，与存储locator严格一致。其6条域名为Google德国/美国站、德语Wikipedia、search.google、Wikipedia、X；不存在误读其它查询哈希的证据。前三条正文来源已持久记录 `source_network_unavailable`，本诊断没有重试。

| 有界对照 | 实际结果 | 名称相关性 | 响应SHA256 |
| --- | --- | --- | --- |
| 企业全称加英文双引号，仅q/format | HTTP200，10条，5034B，1021ms | 标题/摘要完整名称0，“艺霖”0；域名为pkg-zone、PSX、Reddit、GitHub、consolemods、psxhax、archive等 | `105c7518ea4f1416047ccc75e2ac33c2446a4240373281406b6de75bbe59686e` |
| 同一引号q，另加cc=CN、mkt=zh-CN | HTTP200，0条，1062B，980ms | 无候选 | `51038b2ffac9425aa04e71ea78eac5fb76bf9fd2127ce5f227e654f7a47a00eb` |

两个channel标题/链接均回显公开企业名，但URL集合哈希不同，第二次为空。故不能声称“固定同一feed”或“q整体被忽略”已经证明；地区参数确实改变响应。本证据不足以区分市场、分词、未命中后降级、代理或上游行为。cc/mkt仅作为对照参数，未查到本RSS端点的现代稳定契约，未将其自动加入共享实现。

私有收据 `.runtime/baichuan-ai-local/bing-rss-company-relevance.json` 保存原查询重建哈希、来源ID/域名/错误码、两个真实响应/标题/摘要哈希及名称命中指标，无正文、代理地址或凭据。首次脚本两请求完成并写收据后，隔离环境清理了Windows身份变量，ACL步骤报KeyError；未重发请求，随后用原调用者身份给已有文件成功限制ACL，脚本修复为先保存/恢复仅USERNAME/USERDOMAIN。`py_compile`、`git diff --check`实际通过；没有把该初次脚本退出码宣称全程通过。

## 结论与最小下一步

**当前本机RSS对该真实企业研究不可用。** 之前通用查询6条成功仅证明传输/解析/来源安全结构，未验收语义相关性；不得据此开放1283家批次。零相关结果表示发现能力未满足，不表示企业不存在、没有资质或官网。

建议根先保持事实写入和全库后台开关关闭，把企业研究能力门禁分成传输与相关性两项；本轮相关性明确失败。后续若实现最小质量边界，位置应在 `baichuan_research_runtime._search`，保留搜索标题/摘要元数据，确定规则要求标题/摘要出现归一完整公司名（或经已有独立证据关联的信用代码/域名）才成为可抓取候选；其余只记拒绝数量/哈希与 `search_no_relevant_sources`，不抓正文、不调用模型。单纯名称命中只授权候选抓取，仍不能赋予身份、官方或字段verified。不要用泛化后缀“信息科技有限公司”作为相关性证据，也不要把新规则后的结果混同旧缓存；cache需带搜索策略版本并避免复用此次无关URL集。合成测试应覆盖全部无关、相似名称、引用正文注入、别名无独立依据、零结果、缓存策略变更和相关但未核实来源；需再有获准真实相关性样本才能解除门禁。本单元按只读要求未实施这些共享行为变更。

替代路径仍是已有Tavily/Brave适配器的合法可用配置、用户已有获准SearXNG服务，或按既有七类规则来源逐站做独立证书核验器；不能因为RSS失败就宣称这些来源现在可用。上轮官方SearXNG源码/部署及许可证依据见 [公开网络调查](2026-10-17-public-network-investigation.md)；本轮不新装Linux、不购账号、不轮换公共实例、不访问新的企业站点。官方历史RSS描述本就为实验用途：[Bing官方RSS说明](https://blogs.bing.com/search/2005/1/RSS-Feeds-for-Search-Results/)。该历史说明不提供本轮企业相关性保证。

研究覆盖与已核实字段数由根依据真实pilot事务另行报告；此处只读调查不增加覆盖，不撤销或改写旧证据。
