# AI-T12：已入库官网联系缺口，第二组固定12家

时间：2026-10-18约05:12–05:18（北京时间）。本单元仅RO资料研究、冻结候选及隔离校验，根维护者另行审核入库。未修改核心代码、前端、服务、共享SDD、企业或其他业务数据。

本轮重新RO核对104家已入库官网：电话空2、邮箱空39、地址空15，使用`COALESCE(trim(field),'')`包含NULL。排除上一组固定12个ID，按邮箱/地址缺口固定新12家，企业ID集合实际互斥。非空字段及当时版本原样保存在私有cohort。

12家均离线复核已有实际正文与真实可见链接。仅新增3次GET（2家公司），全部HTTP200取得完整原件与正文；每家最多2次，12秒超时，无搜索、模型、重试、登录或TLS绕过。旧失败URL和已读空壳未重发，未把“曾出现过的URL”一概记为失败。

发现邦正旧原件的“查看更多”可见按钮实际绑定同源`/index`，该页面提供实际“联系我们”链接。随后读取[邦正官网](http://www.bangzhengkeji.com.cn/index)及[官方联系页](http://www.bangzhengkeji.com.cn/llxw/)，完整正文含在库法定全名；仅取官方总邮箱与底部办公地址，不取各事业部个人邮箱，不改已有电话。形成1家2原空字段候选。显式HTTP corporate来源保留原协议和未加密标识，未伪造HTTPS。

已实际运行`validate_batch`，PASS；验证进程SQL/socket/DNS均拒绝，实际尝试0。私有批次：`batch-official-contact-gap2.json`，SHA256：`38cdc4c9fc4c1845c39a7fff2ece3ce6e422ecd3b5959be9a804c054708f3da5`。该收据记录的是候选，不代表实际已补。

其他11家逐家保留缺口：

- 瑞达沣、长银和因诺的已有静态页面有空壳；此前渲染正文也未提供可直接补入的本轮空字段。不猜路由或隐藏API。
- 广易、纸贵、青山四纪、图迹及航天信息、公众电气的已读主体正文未找到所需新字段；原非空电话、邮箱及客户案例地址不挪作新值。宽泛“西安市高新区”不伪装成详细地址。
- 星邑已读联系页列不同机构地址，且正文无完整法定名。新实际[商务合作页](https://www.xingyispace.com/contact/list_33.html#nav_33)仍没有可直接绑定的邮箱正文。保留原HTML中实际邮箱图标的mailto属性线索，但未把属性拼造为可见正文；亦未借另一页全名补造逐页身份依据。
- 中科西光官网列三处地址，角色对应不明确，未擅选唯一主联系地址。既有邮箱电话保留。

私有恢复目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/official-contact-gap2-20261018-0512/`，包含固定版本/旧空值、逐家公司原因、实际raw/text、SHA、公开IP固定直连、TLS/HTTP信息和精确文字定位。

| 文件 | SHA256 |
| --- | --- |
| cohort.json | `3be397ae830c334ca3cb65256d3997b3b2f4a0f34bc6c701669b5251c101a47a` |
| journal-final.json | `ac96d073b79bb7468feb4c19d026301a87c06375cc6b00c16f2e524adcf40584` |
| final-receipt.json | `d160739ade5dd4a6699af3a5bdf723c2698cd0d1d92a70bacf6726d17e3667e4` |
| file-manifest.json | `f7cb7589d4670898b2183204cc609582406693f90f75ecbbd1b496ad20c9fa7a` |
| retained-body-review-index.json | `4c5a81bb4c3a5c820eda218fb13a8fd50d6f473f876ce953da814409df760c71` |

复现：私有`fetch-visible-contact.py <cohort索引> <实际可见URL>`保留每次意图及收据，不自动重试/重定向；`validate-offline.py`用company-test Python运行禁SQL/网络批次校验；`freeze-final.py`离线核账并独占创建新文件。冻结输出不得覆盖，为复测另建目录且不得重复外发已完成请求。网站声明不等于工商或发证机构核实；本单元没有新增资质核实，也不宣称全部12字段完成。
