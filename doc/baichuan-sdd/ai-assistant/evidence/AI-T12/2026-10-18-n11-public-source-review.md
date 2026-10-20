# AI-T12 N11a/N11b 公开资料候选复核

生成时点：2026-10-18 03:13（Asia/Shanghai）。本记录为独立研究候选交付；实际应用由 root 另行审核、记录，本代理未写业务库。不能据此称全库资料补齐或联系方式已独立核实。

固定来源为 selection-next-after-w12.json（SHA256 325ef186a48b6bff774d8937f57e61d3f2297a686fd30099581cacf1ed7b8c68）实际键 no_usable_retained_lead 的 [240:260]、[260:280]，各20家，与 N12 [280:320] 互斥。初次全名发现覆盖新增0；本轮为具体字段/所在地的第二层研究。排除既有夜间、L、联系页、HTTP、N cohort，并只读核对当前 ID、名称、版本及全部联系字段。

| 单元 | 新定向检索 | 新公开URL尝试 | 实际HTTP200目标正文 | 候选企业/字段 | 来源分型 |
|---|---:|---:|---:|---:|---|
| N11a | 20（5次搜索工具调用） | 6 | 6 | 6/11 | directory4、industry1、encyclopedia1 |
| N11b | 20（5次搜索工具调用） | 3 | 2 | 2/4 | directory2 |

N11a 在 03:11:51、N11b 在 03:12:42 实际调用现有 validate_batch 通过；校验阶段将 sqlite3.connect、socket.connect、create_connection、getaddrinfo 设为拒绝，验证无SQL及网络依赖。每组20条当前数据库记录采用 mode=ro/query_only 短连接，与候选生成前版本及字段逐一完全相同；连接立即关闭。原档、UTF-8正文、来源 SHA 与字符 locator 均实际复算。0模型调用、0企业写入、0前端/服务改动。

## 实际可审候选

| 企业 | 字面候选 | 已读取公开来源 | 边界 |
|---|---|---|---|
| 西安鸿煊智能电子有限公司 | 地址；西安市 | [建设招投标网](https://www.zhaotoubiaowang.com/company/detail_for_19328348.html) | 主体经营地址，联系更新时间未知；平台400及过期证书不采 |
| 陕西经达石化装备工程有限公司 | 地址；邮箱 | [中国企业库](https://www.qiyeku.cn/huangye/1414428.html) | 西咸新区不强映射市；平台子域不作官网 |
| 西安中创新能网络科技有限责任公司 | 注册地址 | [陕西股权交易中心](https://www.sxeec.com/company/companyDetail?enId=303272) | 地址原文空格括号保留；页脚交易中心地址/邮箱排除 |
| 西安中兴精诚通讯有限公司 | 注册地址 | [住建数据云](https://www.ezhujian.cn/company/detail?no=11996798) | 联系日期未知，原电话/城市不覆盖；过期证书不核实 |
| 中陕核宜威新能源有限公司 | 地址；西安市；邮箱 | [CNPP](https://www.cnpp.cn/pinpai/127868.html) | 网站明确提醒可能过时；联系更新时间未知，非独立核实 |
| 西安明景技术有限公司 | 地址；西安市 | [建企百科](https://baike.cbi360.net/2521737/) | 基本信息公开披露；2025经营统计不等于地址更新日期 |
| 陕西新一建筑劳务有限公司 | 地址；西安市；邮箱 | [中国企业库](https://www.qiyeku.cn/tag/company715af6-2.html) | 目标独立主体块，非邻企；2022裁判同址仅历史线索，不声称当前核实 |
| 陕西誉晟智能科技工程有限公司 | 地址 | [水滴标讯](https://biaoxun.shuidi.cn/company-detail/d651da174d8be048621572499b6556f9.html) | 联系日期未知；原文仅西安、不推西安市；动态联系人加载不当已读取 |

全部15字段仅候选生成时真实空白字段；无官网候选。地址/邮箱仍属公开披露，不自动认定工商登记/联系有效性/证书核实。

## 失败、冲突与未知

N11a：CNPP 显式官网 http://www.zshevi.com/ 及榆林方广的 lubanlebiao.com 线索被历史失败 host 排除，均0新GET，不能拿搜索摘要补官网或地址。西安中城卫结果提示2023更名、2024搬迁，与旧名/旧合同地址有身份及时点差异，保留冲突，不静默更名或套新地址。陕北矿业运维分公司不借母公司页脚联系，医院/研究所采购人联系不转给中标人；2023采购与2021招聘地址仅历史线索。

N11b：m.qiyeku.cn 顺泽页面一次公开GET超时，未重试、无正文候选；相邻佳旭公司地址/电话不可挪用。方达2022暂停认证通知的0519电话属于认证机构；振华2025采购联系电话属于采购人705所；陕西元成/西安国电元成与元成电力主体不可混同。广信2023母公司债券披露为历史子公司地址，母公司当前页脚不转移。其余逐家缺口及检索存档见各 frozen journal。

所有访问使用正常TLS验证、公共IP校验、无继承代理、无自动重定向、无失败重试、每家公司最多2URL。新尝试共9URL，8份HTTP200实际目标正文、1超时；搜索结果存档仅用于线索，不替代正文。无验证码绕过。

## 冻结与恢复

私有目录：.runtime/baichuan-ai-local/independent-enrichment-20261017。

- N11a batch-leads-n11a.json：SHA256 1fd45d25c3735fd6c602c928e05e37a1284bd68db4c68b47d1158eabe04728b6。
- N11a journal：SHA256 6bb1c5b5c0a65013b18208dd6b87f080ce3d92f1bd900b81dfd870087929f6af。
- N11b batch-leads-n11b.json：SHA256 12a629e4733e5b314dce0ae470377da353f098f99bb7248039c7363c39e75924。
- N11b journal：SHA256 c4c11fba185220c06349f7ecbfafdc8eb68531f07fed5d6be0b8199acb9c6b5d。

各组均保留 cohort、initial、每5份读页检查点、前10家复核检查点、搜索5份归档、raw/body、final-receipt、freeze-index。下一步 root 独立读取完整正文并审核是否采纳，之后由 root 唯一 apply 及重放核账；原候选/原证据不得回写成应用结果。
