# AI-T12 当前电话空字段249家：电话目的按ID分层

固定数据库快照为2026-10-18 06:48:01.178239 +08:00，owned portal.sqlite3 的mode=ro/query_only读取得到249家电话原空企业。之后根代理如维护裕方，属于后续授权维护，不改变此快照分母。仅此次只读分层，不维护persistent queue、coverage或业务字段。

| 互斥研究目的类别 | 企业数 | 证据含义 |
|---|---:|---|
| 完整法定名明确电话query执行记录 | 193 | 原始journal query与search_attempted绑定；搜索档可用性另列 |
| 仅混合“电话 OR 地址 OR 官网”查询 | 55 | 有电话关键词，不等于完成专项电话来源核查 |
| 号码专项复核 | 1 | 培荣旧phone_recheck，保留独立当前号码核实缺口 |
| 合计 | 249 | 不表示249电话已全部研究或核实 |

交叉指标不能与上述互斥分层相加：102家有已完成电话来源专项/phone cohort；18家旧正文有号码样式，但号码不当然属于目标主体。限制/排除标记按原文定位：12家掩码/隐藏、21家访问受限、33家平台客服排除、55家其他主体/采购代理排除；这些标记可重叠，不表示企业没有电话。

当前留存证据边界中，无电话目的记录的新企业余集为0；这不等于全部专项完成。后续可继续处理55家仅混合查询的明确新来源/专项核查策略，复用既有原文并排除已读URL和失败host，不能机械重复旧查询。20家只有历史journal执行声明，缺任何原搜索档绑定，单列档案缺口，不能称为独立工具执行实证，也不能反向视为从未搜过。全部249家逐ID列表在私有classification-by-ID-v3.json及.md，原始query、完成cohort、typedledger、body信号和限制具体refs逐项保留。

初版按完整法定名+电话关键词筛选，漏掉培荣的号码专项复核；v3已更正。v1/v2为已取代草稿，不能据其“1家新目的余集”继续重复搜索。

陕西培荣全盛建设工程有限公司（cbda8c1f-cbbb-57df-ba6b-5ba091a15a64）保持电话pending，本单元不制批：
- 原档research-night-w10.json#/items/58/phone_recheck记录两条15191234560号码复核query，绑定w10-phone-specific-search.json，仅同一企业库来源，没有独立当前号码核实。
- 原[单企业目录](https://www.qiyeku.cn/huangye/6182017.html)原HTML52082字节，实际SHA daef4b4f62745a04ecbcc753496ec01a90d83cbe6db059f5801360a7d5477feb；正文规范化SHA fc50d5e8de978918f077fef63f5a60e2af819564afd22f144847c6e73b8d73c1，与原journal正文相符。完整主体块字符190:1409，15191234560在原HTML连续字面出现4次，未从邮箱拼接/还原。原HTML此前未在此journal记录raw SHA，此次重新计算不冒充此前绑定。
- 同站[行业目录](https://www.qiyeku.cn/huangye/1785_289.html)原HTML72456字节SHA bb02a10ced7140b4cc449bbddd2a2dc37642db4981cc738cf20f0832c1110907；正文SHA b4489b84a22944d3c6ceba8a95131e436665b5003cd4a2982c9764db65439982，主体块2487:2819亦有该电话。同出版方重复不构成独立验证。
- 13631151688与13322908998为平台客服/合作电话，排除。未见显式AI生成标记不能验证信息来源；目录模板、连续数字及缺独立核实保留，不把格式正常当真实可用。

实际离线检查150份输入hash、889个JSON定位引用、297个query指针与272条搜索档hash绑定通过；后二者是证据引用数，不能当真实搜索次数。SQL/socket/DNS拒绝保护自测通过，实际审计验证三类外部尝试0。审计0GET、0模型、0业务写。

私有目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/phone-purpose-current-empty-audit-20261018-0648/`。

| 最终证据 | SHA256 |
|---|---|
| current-empty-phone-RO-snapshot.json | cecee5ff4d1bf437dee8a4a56cbee3402023c16c4efa5a3ba8039afb23988c01 |
| classification-by-ID-v3.json | c73999b8e511fae09532f8762c29d132a3d5d7186c0c6461c6f3acba30e2666a |
| fresh-purpose-remainder-v3.json | 0a05f9fe607b639d638884d0651963f67621bf3bb8a119f86b887817bf959780 |
| mixed-OR-only-new-strategy-v3.json | ee402d7d1d5f66dad35e2b2dd884680f32f175192d4545eee747624f617cc3c1 |
| peirong-original-archive-review-v3.json | 357d5998332e85949b400619706eb94f05848bdeb02659bf6547498b8542a569 |
| execution-archive-gap20-addendum.json | a162cd308c815dbe76a7c58ead53ab2429e583b1fce924d1658a54732d5e9740 |
| validation-offline-v3.json | f92720a046f4cfa6cb62b992c3564f101980a6141f45aca09e1e27acb1c2a908 |
| frozen-files-v3.json | e69b9e0d2ab4841941f548c05a311e8e0e2ce78d412828e887094cd351ef164b |
| final-receipt-v3.json | 2db6d5479da99fbd8126d5f6337269d851fd15bd9ce925f5cbd6d2432a29e01d |

官网查询或网页出现号码均未直接作为电话专项完成条件。未知不等于没有，不宣称资料全部补齐。

