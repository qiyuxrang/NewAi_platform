# AI-T12 Q6：固定50家 ITSS 公开证书只读研究

冻结时点：2026-10-18 03:57（北京时间）。本单元仅准备来源可追溯的证书公开披露候选，**0主库/企业/证书/事实写入，0模型调用，0前端/服务/核心源码改动**。没有提升verified，也没有调用证书维护函数。根代理唯一审核并决定后续路径，不代表证书已经核实入库或全库资质完成。

## 名单、公开路由和请求边界

实际原ITSS声明248行、242个不同企业UUID，6家各2行原件保留。固定排除Q4三家及Q5二十家，从剩余219家UUID升序取下50，不扩到其他企业。manifest含全部原声明、映射证书与当前版本，SHA256：`9cfb7f817945ace876c38d14b7e908458e7695991c99fd52b63cec4bae1a20b2`。

复用Q4已存[ITSS公开获证单位表单](https://www.itss.cn/web/itss/c/xxcx/cert)、声明JS及真实详情模板，0新页面/JS读取，0第三方JS执行或代码采用。没有猜测接口/域名。实际每家公司完整原名称查询一次，原公开字段itssType=YW，合法取消状态勾选（URL不传validFlag），详情仅用返回的certificateId及实际公开模板路由。每家上限1列表+2精确详情，整批上限150GET；验证码/登录/429/明确禁止即整批停止、未处理保留pending，0重试。

本轮实际50列表 + 34详情JSON = **84GET，全HTTP200**。串行完成到下一开始间隔最小1.0000447秒，最慢请求0.2628563秒，低于12秒上限。没有权限挑战、失败重试、未展开精确行、分页或pending。实际读取意图/URL/参数/原始字节/body/SHA/时间/正常TLS/公共IP均存。

## 公开记录与未知

34家公司各1条完整主体公开记录，实际均披露“有效”：三级32条、二级2条。全部与原PRESENT等级逐项对照一致，没有把升级事项误当新旧等级冲突或自动更改旧等级。

startDate按原官方模板只保存“获证日期”，getDate为“发证日期”，endDate为“到期日期”；再评估记录的获证和发证日期可能不同，均保留原字面。**valid_from、独立issuer、标准号、specific scope都未知**，不由获证/发证/业务领域推断。pgjg仅“评估机构”，不当issuer。公开状态原文保留，不升级事实verified，不宣告确定匹配满足。

| 精确主体（实际详情JSON） | 证号 | 级别 | 获证日期 | 发证日期 | 到期日期 | 事项 |
| --- | --- | --- | --- | --- | --- | --- |
| [陕西公众信息产业有限公司](https://www.itss.cn/api/itss/web/certificate/44ca393d3b674dc2a5a94a4118a496d0) | ITSS-YW-3-610020240029 | 三级 | 2024-01-04 | 2024-01-04 | 2027-01-03 | 监督评估 |
| [西安雷迪信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/9725acdaa4af4e1aabf5bb5f7ce85d91) | ITSS-YW-3-610020250892 | 三级 | 2025-07-29 | 2025-07-29 | 2028-07-28 | 监督评估 |
| [陕西一二三数字信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/8b06ac2f98ee44819594da5ad060a847) | ITSS-YW-2-610020260036 | 二级 | 2026-05-28 | 2026-05-28 | 2029-05-27 | 升级 |
| [西安赞美网络科技有限公司](https://www.itss.cn/api/itss/web/certificate/5a8bee2a95ce46c1a39ce18009e10d7a) | ITSS-YW-3-610020260261 | 三级 | 2026-02-10 | 2026-02-10 | 2029-02-09 | 初次申请 |
| [延安通和电业有限责任公司](https://www.itss.cn/api/itss/web/certificate/a9a1082f6dde4c0a9c5b8b2151547883) | ITSS-YW-3-610020251263 | 三级 | 2025-11-14 | 2025-11-14 | 2028-11-13 | 初次申请 |
| [西安秦汉瑞达信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/774b9a95d18d43ea897720d2c5848f44) | ITSS-YW-3-610020251241 | 三级 | 2025-11-10 | 2025-11-10 | 2028-11-09 | 监督评估 |
| [西安栎安科技有限公司](https://www.itss.cn/api/itss/web/certificate/84e2072b834148c48d8b7d3c62500c93) | ITSS-YW-3-610020260100 | 三级 | 2026-01-23 | 2026-01-23 | 2029-01-22 | 初次申请 |
| [西安卓精电子科技有限公司](https://www.itss.cn/api/itss/web/certificate/bc2214edc7894338a637455af0a3612f) | ITSS-YW-3-610020260127 | 三级 | 2026-01-23 | 2026-01-23 | 2029-01-22 | 初次申请 |
| [西安峰频能源科技有限公司](https://www.itss.cn/api/itss/web/certificate/11b2e160853f45b493f1a03e6fb32fbe) | ITSS-YW-3-610020240458 | 三级 | 2024-03-26 | 2024-03-26 | 2027-03-25 | 监督评估 |
| [西安华利达数码科技有限公司](https://www.itss.cn/api/itss/web/certificate/e608a1b18aaa4d83958523fa9704427e) | ITSS-YW-3-610020251119 | 三级 | 2025-10-27 | 2025-10-27 | 2028-10-26 | 监督评估 |
| [西安拓峰电子科技有限公司](https://www.itss.cn/api/itss/web/certificate/d526bc2025ee4bffbba74df4735d2813) | ITSS-YW-3-610020250215 | 三级 | 2025-02-25 | 2025-02-25 | 2028-02-24 | 监督评估 |
| [陕西关天大数据有限责任公司](https://www.itss.cn/api/itss/web/certificate/f298cbeb899c43f7a8d465b7e65deff5) | ITSS-YW-3-610020240044 | 三级 | 2024-01-04 | 2024-01-04 | 2027-01-03 | 监督评估 |
| [陕西鲲达信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/cd236cb1418c45459b920c0f364af157) | ITSS-YW-3-610020250677 | 三级 | 2025-06-25 | 2025-06-25 | 2028-06-24 | 监督评估 |
| [西安长驰亿威科技有限公司](https://www.itss.cn/api/itss/web/certificate/7ce7f75065244d339b749f87ff71bb57) | ITSS-YW-3-610020251448 | 三级 | 2025-12-22 | 2025-12-22 | 2028-12-21 | 初次申请 |
| [陕西秦锋数码科技有限公司](https://www.itss.cn/api/itss/web/certificate/a05fe37964b040feb31ab39f4f2ef934) | ITSS-YW-3-610020231337 | 三级 | 2023-10-23 | 2026-07-06 | 2029-10-22 | 再评估 |
| [西安航天自动化股份有限公司](https://www.itss.cn/api/itss/web/certificate/d07493a5c9624fd9bb159ab46679258e) | ITSS-YW-3-610020241704 | 三级 | 2024-12-19 | 2024-12-19 | 2027-12-18 | 监督评估 |
| [西安奥卡云数据科技有限公司](https://www.itss.cn/api/itss/web/certificate/ddbced8bf2b345999fc3f237b30d3fac) | ITSS-YW-3-610020230315 | 三级 | 2023-03-07 | 2026-01-19 | 2029-03-06 | 再评估 |
| [陕西工业云中心管理运营有限公司](https://www.itss.cn/api/itss/web/certificate/c269cb3baa8a42bcbcb5ea68596f6a35) | ITSS-YW-3-610020260027 | 三级 | 2026-01-08 | 2026-01-08 | 2029-01-07 | 初次申请 |
| [榆林金马巴巴网络科技有限公司](https://www.itss.cn/api/itss/web/certificate/90e272f83f2e4915aadd7723bfc4c81b) | ITSS-YW-3-610020251405 | 三级 | 2025-12-15 | 2025-12-15 | 2028-12-14 | 初次申请 |
| [陕西延长石油数智科技有限责任公司](https://www.itss.cn/api/itss/web/certificate/fd4086fc854d42f7a1ade9be3825e28d) | ITSS-YW-3-610020251256 | 三级 | 2025-11-10 | 2025-11-10 | 2028-11-09 | 监督评估 |
| [陕西安泰通讯有限责任公司](https://www.itss.cn/api/itss/web/certificate/a019b5a771fe46d581e47da14b9e5738) | ITSS-YW-3-610020240364 | 三级 | 2024-03-11 | 2024-03-11 | 2027-03-10 | 监督评估 |
| [陕西省通信服务有限公司](https://www.itss.cn/api/itss/web/certificate/b500ae007bce42f6989f6aefa3ede04c) | ITSS-YW-3-610020250669 | 三级 | 2025-06-25 | 2025-06-25 | 2028-06-24 | 监督评估 |
| [西安博展电力技术有限公司](https://www.itss.cn/api/itss/web/certificate/cde16ae657c746bdb4308c8f92519d99) | ITSS-YW-3-610020240441 | 三级 | 2024-03-26 | 2024-03-26 | 2027-03-25 | 监督评估 |
| [陕西亿海信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/c924662e831f4f83964957d57d846846) | ITSS-YW-3-610020261117 | 三级 | 2026-09-30 | 2026-09-30 | 2029-09-29 | 初次申请 |
| [西安瑞蓝创软件科技有限公司](https://www.itss.cn/api/itss/web/certificate/56d30370875d438795239a227fcbda49) | ITSS-YW-3-610020251244 | 三级 | 2025-11-10 | 2025-11-10 | 2028-11-09 | 监督评估 |
| [神木市智慧城市发展研究有限公司](https://www.itss.cn/api/itss/web/certificate/1864d60e1fc6486c8fc144e758e94df6) | ITSS-YW-3-610020250021 | 三级 | 2025-01-08 | 2025-01-08 | 2028-01-07 | 监督评估 |
| [陕西陕煤榆北煤业有限公司](https://www.itss.cn/api/itss/web/certificate/dc58f3d5814642eabbbafe5c2b6c9128) | ITSS-YW-3-610020231638 | 三级 | 2023-11-27 | 2023-11-27 | 2026-11-26 | 监督评估 |
| [陕西长大瑞通交通控制工程有限公司](https://www.itss.cn/api/itss/web/certificate/839d9e852c8f4de38e73dde70c969a07) | ITSS-YW-3-610020251447 | 三级 | 2025-12-22 | 2025-12-22 | 2028-12-21 | 初次申请 |
| [西安能控安远信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/3265751288554282abafc81643517bdc) | ITSS-YW-3-610020240948 | 三级 | 2024-07-16 | 2024-07-16 | 2027-07-15 | 监督评估 |
| [陕西众维信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/afb1517d50a04e738b35df18303b73df) | ITSS-YW-3-610020231562 | 三级 | 2023-11-13 | 2023-11-13 | 2026-11-12 | 监督评估 |
| [西安恪诚电子科技有限公司](https://www.itss.cn/api/itss/web/certificate/6e93db75ce0f494f83dff579aee9174e) | ITSS-YW-2-610020260067 | 二级 | 2026-09-04 | 2026-09-04 | 2029-09-03 | 升级 |
| [西安阔海信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/2f578e09147a49b1b3317b75e45f2603) | ITSS-YW-3-610020241694 | 三级 | 2024-12-19 | 2024-12-19 | 2027-12-18 | 监督评估 |
| [陕西安聚电子科技有限公司](https://www.itss.cn/api/itss/web/certificate/cb25e8b22efc408fa9b13c617b9e4fd4) | ITSS-YW-3-610020260375 | 三级 | 2026-03-26 | 2026-03-26 | 2029-03-25 | 初次申请 |
| [陕西易维计算机技术服务有限公司](https://www.itss.cn/api/itss/web/certificate/f2f24f637f8242019912bd50d464b393) | ITSS-YW-3-610020240016 | 三级 | 2024-01-02 | 2026-09-03 | 2030-01-01 | 再评估 |

另16家公司本次列表total0，仅保持未知：陕西公众电气股份有限公司、陕西智维中兴电子科技有限公司、铜川易源电力实业有限责任公司、陕西智引科技有限公司、西安归毂智能科技有限公司、陕西中安科创信息技术有限公司、中航电测仪器(西安)有限公司、自然资源部陕西基础地理信息中心(自然资源部陕西测绘资料档案馆)、中交(西安)数字产业有限公司、赛辰(西安)信息科技有限公司、陕西成睿科技有限责任公司、西安交大长天软件股份有限公司、国网数字科技(陕西)有限公司、大道(西安)信息技术股份有限公司、陕西天成网络科技有限公司、西安壹零软件有限公司。没有额外换名、重试或扩大企业；列表空不等于无证。

虽然请求未传validFlag，但服务器在参数省略时是否有内部默认状态过滤未独立审计；所有实际结果“有效”不证明不存在暂停/撤销/历史证书，也不声称穷尽所有状态。

## 实际校验与恢复点

网络执行前实际完成默认inert入口与SQL连接/socket连接/create_connection/DNS四种拒绝自检，inert执行新增0SQL/网络尝试、0文件。执行后再次完成四种离线拒绝自检。全部84份raw/body SHA真实核对，34条详情字段与各自列表逐项一致；同一目标最多1详情，未达2上限。

最终短SQLite mode=ro/query_only复核50家name/version、全部原ITSS声明和已映射证书都与固定名单时相同。每家公司请求后立即持久化journal，实际保存10/25/50读取检查点及25家离线复核检查点。仅写研究目录、独立证据，不编辑共享SDD/checkpoint/coverage。没有伪称通过普通联系字段validate_batch，此封套不是可执行维护batch。

私有恢复目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/qualification-q6-itss/`。包含manifest、journal、原档/连续全文摘录/字符定位、候选、inert护栏收据、实际请求收据、等级对照及独立冻结索引。冻结原字节不随根代理后续审核/应用改写。

- candidates.json SHA256：`899d8496f9d54fc872690a4ebacc34bc9b356fc90a8f83f25df23b36f8b75e1d`
- journal.json SHA256：`0191bca88c3777a67fd5b383b8950f1ec797682d2d3fe3f3c2cbc90e87a6a2e5`
- final-receipt.json SHA256：`d9bd84cd746680aece9be9c1ecfc9092c7e55da50a60f278a33787c56595b439`

首次发现覆盖和实际资料补入均未因本研究增加；34条是公开证书证据候选，16家是本次未知，全部50家原声明与未核实状态仍保留。
