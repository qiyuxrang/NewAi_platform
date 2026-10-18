# AI-T12 Q7：固定50家 ITSS 公开证书只读研究

冻结时点：2026-10-18T04:01:53.313042+08:00。本单元只准备可追溯公开记录，**0主库/企业/证书/事实写入、0模型调用、0前端/服务/核心源码改动**。没有调用证书维护函数或提高verified。根代理唯一审核决定后续，不表示证书已核实入库或全库资质完成。

## 固定名单和真实读取边界

原ITSS声明248行、242个不同企业UUID，6家各2行全部保留。排除Q4三家、Q5二十家、Q6五十家，从剩余169家按UUID升序固定取50家，不扩大范围。manifest保存全部原声明、已有映射证书和版本，SHA256：`3e559557b93466708cdaa263ae58b0e5e07466076807190c9d8d54296f100252`。

复用Q4保存的[ITSS获证单位公开表单](https://www.itss.cn/web/itss/c/xxcx/cert)、实际声明JS和详情模板；0新JS/HTML GET，0脚本执行或代码采用，未假设许可证。每家仅一次完整原名查询，原表单itssType=YW，不传合法未勾选的validFlag；详情只取实际列表certificateId及已声明路由，不猜路径。上限每家1列表+2详情JSON，整批150GET；正常TLS、公共IP、无代理/重定向、2MB限额、12秒超时、串行间隔至少1秒、0重试，验证码/登录/429/明确禁止即整批停止并留pending。

实际50列表+36详情JSON=**86GET，全部HTTP200**。完成到下一开始间隔最小1.0000658秒，最慢请求0.2678425秒。没有挑战/分页未展开/未展开精确行/pending；本轮每家最多1详情，没有达到2详情限额。全部实际URL、intent、raw/body字节、SHA、时间和公开路由证据保留。

## 字面等级、日期和未知

36家公司各1条精确主体公开记录，原文均为“有效”：三级31、二级3、一级1、通用要求1。35条可比较等级逐项对照原PRESENT等级一致；没有自动更改等级。陕西陕煤陕北矿业有限公司信息技术运维分公司是完整分支主体，公开certificateName为“通用要求”，证号ITSS-YW-YH-610020230017；原两条声明grade均空，保持未知，不强映射一级至四级，也不把母公司证书移给分支。

首次离线冻结工具将certificateName局限为四个等级，实际“通用要求”触发断言并停止；失败诊断和当时25家网络读取检查点保留；失败发生于第25家离线中段写出前，没有首轮离线中段文件。仅调整本单元私有审计工具接纳原字面后重新离线核验，**0 HTTP重发、0核心规则放宽**。

startDate按已保存官方模板标签保留“获证日期”，getDate为“发证日期”，endDate为“到期日期”；不把获证日期推为当前证书valid_from。独立issuer、标准号、specific scope和valid_from继续未知，pgjg仅评估机构不作issuer。公开“有效”不升级verified或推断确定匹配满足。

| 精确主体（实际详情JSON） | 证号 | 公开类别/级别 | 获证日期 | 发证日期 | 到期日期 | 事项 |
| --- | --- | --- | --- | --- | --- | --- |
| [陕西时华智慧电子科技有限公司](https://www.itss.cn/api/itss/web/certificate/c47c662660e046bd9f067e61fe92855f) | ITSS-YW-3-610020260135 | 三级 | 2026-01-26 | 2026-01-26 | 2029-01-25 | 初次申请 |
| [西安兴瀚创邑信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/a30131a3b80a4322b3d7666bbd8198ea) | ITSS-YW-3-610020260859 | 三级 | 2026-08-04 | 2026-08-04 | 2029-08-03 | 初次申请 |
| [西安盛行网络科技有限公司](https://www.itss.cn/api/itss/web/certificate/b96ca006f9354597b0cd9cf24a68fed8) | ITSS-YW-3-610020250181 | 三级 | 2025-02-24 | 2025-02-24 | 2028-02-23 | 监督评估 |
| [陕西地矿科技产业股份有限公司](https://www.itss.cn/api/itss/web/certificate/1ded8fdd93654682b44abcd4d85152f9) | ITSS-YW-3-610020230994 | 三级 | 2023-08-14 | 2026-07-02 | 2029-08-13 | 再评估 |
| [西安西热电站信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/a3625ced2fbd4e00bf46ff35538711e8) | ITSS-YW-3-610020251509 | 三级 | 2025-12-29 | 2025-12-29 | 2028-12-28 | 初次申请 |
| [陕西西联数科科技有限公司](https://www.itss.cn/api/itss/web/certificate/2be66638529b4b52938b655ac8622df3) | ITSS-YW-3-610020260209 | 三级 | 2026-02-03 | 2026-02-03 | 2029-02-02 | 初次申请 |
| [西安华盛通信有限公司](https://www.itss.cn/api/itss/web/certificate/e38d2ec5c14c43b78ec73c29252fde3a) | ITSS-YW-3-610020240410 | 三级 | 2024-03-19 | 2024-03-19 | 2027-03-18 | 监督评估 |
| [陕西小伙伴网络科技有限公司](https://www.itss.cn/api/itss/web/certificate/2f443b7abb6a402e9c21b8e112a71f39) | ITSS-YW-3-610020260544 | 三级 | 2026-05-25 | 2026-05-25 | 2029-05-24 | 初次申请 |
| [西安佳创科技发展有限公司](https://www.itss.cn/api/itss/web/certificate/50e5f359e05b481891d1c3036fa82f19) | ITSS-YW-3-610020231250 | 三级 | 2023-10-10 | 2026-04-30 | 2029-10-09 | 再评估 |
| [西安睿瑶电子科技有限公司](https://www.itss.cn/api/itss/web/certificate/55c6c97ca89b4229b6831d088b4de2ef) | ITSS-YW-3-610020230210 | 三级 | 2023-01-29 | 2025-10-20 | 2029-01-28 | 再评估 |
| [西安唯海智慧安防技术有限公司](https://www.itss.cn/api/itss/web/certificate/496fd1c86cd8459da0a3293a6f91a8f1) | ITSS-YW-2-610020250113 | 二级 | 2025-10-03 | 2025-10-03 | 2028-10-02 | 监督评估 |
| [陕西航泰电气股份有限公司](https://www.itss.cn/api/itss/web/certificate/740e32c68e5e46498a4474a856a93767) | ITSS-YW-3-610020230605 | 三级 | 2023-05-23 | 2026-01-30 | 2029-05-22 | 再评估 |
| [西安长城数字软件有限公司](https://www.itss.cn/api/itss/web/certificate/db1e0bb74b074719be0d7c7268d47f84) | ITSS-YW-3-610020240217 | 三级 | 2024-02-06 | 2024-02-06 | 2027-02-05 | 监督评估 |
| [陕西成缘升信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/bf67b258584c48b8be8a37d00adc10cf) | ITSS-YW-3-610020250077 | 三级 | 2025-01-27 | 2025-01-27 | 2028-01-26 | 监督评估 |
| [陕西北佳信息技术有限责任公司](https://www.itss.cn/api/itss/web/certificate/731a77fd87374700b0bcda006591538a) | ITSS-YW-1-610020240011 | 一级 | 2024-11-25 | 2024-11-25 | 2027-11-24 | 监督评估 |
| [陕西省大数据集团有限公司](https://www.itss.cn/api/itss/web/certificate/3869b1bdda9b424a8a76fd015fe1ad25) | ITSS-YW-2-610020250142 | 二级 | 2025-12-12 | 2025-12-12 | 2028-12-11 | 升级 |
| [西安博深安全科技股份有限公司](https://www.itss.cn/api/itss/web/certificate/d8f9c4962ef54727b74a60358f6ab8f2) | ITSS-YW-3-610020250202 | 三级 | 2025-02-24 | 2025-02-24 | 2028-02-23 | 监督评估 |
| [陕西陕煤陕北矿业有限公司信息技术运维分公司](https://www.itss.cn/api/itss/web/certificate/02d32c5b224340b6be51e8e12a08315b) | ITSS-YW-YH-610020230017 | 通用要求 | 2023-12-20 | 2023-12-20 | 2026-12-19 | 监督评估 |
| [神木市信息产业发展集团有限公司](https://www.itss.cn/api/itss/web/certificate/59d3472da2d24f2f9ee5a4374f54ec07) | ITSS-YW-3-610020260840 | 三级 | 2026-07-27 | 2026-07-27 | 2029-07-26 | 初次申请 |
| [西安中兴精诚通讯有限公司](https://www.itss.cn/api/itss/web/certificate/1874e8d169914fc680f996044214950d) | ITSS-YW-3-610020260612 | 三级 | 2026-06-08 | 2026-06-08 | 2029-06-07 | 初次申请 |
| [陕西北石佳华信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/fa764ce0a76c41a3be4c542f1c44fb69) | ITSS-YW-3-610020250174 | 三级 | 2025-02-24 | 2025-02-24 | 2028-02-23 | 监督评估 |
| [西安佐佑民科技有限公司](https://www.itss.cn/api/itss/web/certificate/6a08d273c2ad4c68906cc3cd1b4df8ad) | ITSS-YW-3-610020250104 | 三级 | 2025-01-27 | 2025-01-27 | 2028-01-26 | 监督评估 |
| [西安图讯信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/1e4b3cddb1a84889880f39bd4fe75899) | ITSS-YW-3-610020260213 | 三级 | 2026-02-06 | 2026-02-06 | 2029-02-05 | 初次申请 |
| [振华智造(西安)科技有限公司](https://www.itss.cn/api/itss/web/certificate/ca737e72de8d42da9018c7d86de6f444) | ITSS-YW-3-610020231506 | 三级 | 2023-11-03 | 2026-07-06 | 2029-11-02 | 再评估 |
| [陕西方达科技发展有限公司](https://www.itss.cn/api/itss/web/certificate/43e21ab44dd14cb19b988c4a2eb4ffb1) | ITSS-YW-3-610020251485 | 三级 | 2025-12-23 | 2025-12-23 | 2028-12-22 | 初次申请 |
| [陕西利元电力设备有限责任公司](https://www.itss.cn/api/itss/web/certificate/8786ea26df644472801aecfacd1b3473) | ITSS-YW-3-610020241330 | 三级 | 2024-09-30 | 2024-09-30 | 2027-09-29 | 监督评估 |
| [西安昺洲信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/6344d4fffc114b6ea322eba49d133bd3) | ITSS-YW-3-610020240261 | 三级 | 2024-02-06 | 2024-02-06 | 2027-02-05 | 监督评估 |
| [陕西数图行信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/f66f0ad777c84c79982ca13d5c2db0eb) | ITSS-YW-3-610020231693 | 三级 | 2023-12-04 | 2023-12-04 | 2026-12-03 | 监督评估 |
| [陕西丝路金融信息发展有限公司](https://www.itss.cn/api/itss/web/certificate/63d9eb88d5c34317ba2305c15dacf42c) | ITSS-YW-2-610020240090 | 二级 | 2024-09-09 | 2024-09-09 | 2027-09-08 | 监督评估 |
| [西安西驰信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/06c0a407b5ce496c98835271f2a89373) | ITSS-YW-3-610020251445 | 三级 | 2025-12-22 | 2025-12-22 | 2028-12-21 | 初次申请 |
| [神木市神信蓝盾科技有限公司](https://www.itss.cn/api/itss/web/certificate/aa831852e2834533aa8e654bd5f58f52) | ITSS-YW-3-610020250023 | 三级 | 2025-01-08 | 2025-01-08 | 2028-01-07 | 监督评估 |
| [西安天地隆电子科技有限公司](https://www.itss.cn/api/itss/web/certificate/5d812cc31726466e964a6c2957a212c9) | ITSS-YW-3-610020250488 | 三级 | 2025-05-13 | 2025-05-13 | 2028-05-12 | 监督评估 |
| [西安民航凯亚科技有限公司](https://www.itss.cn/api/itss/web/certificate/fc06822d4db340c9aa45163e816a3694) | ITSS-YW-3-610020260954 | 三级 | 2026-08-18 | 2026-08-18 | 2029-08-17 | 初次申请 |
| [陕西淘丁数据科技有限公司](https://www.itss.cn/api/itss/web/certificate/9b221441eaad4025a5677b9dc15bd574) | ITSS-YW-3-610020260563 | 三级 | 2026-05-25 | 2026-05-25 | 2029-05-24 | 初次申请 |
| [陕西睿联信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/e6d78985136f4e18a33f0ec0a5e29ddb) | ITSS-YW-3-610020230781 | 三级 | 2023-06-30 | 2026-06-01 | 2029-06-29 | 再评估 |
| [中国移动通信集团陕西有限公司](https://www.itss.cn/api/itss/web/certificate/5f333fe4aa054c68b170d1fd097f4169) | ITSS-YW-3-610020250182 | 三级 | 2025-02-24 | 2025-02-24 | 2028-02-23 | 监督评估 |

另14家本次公开列表无精确主体记录，仅保持未知：陕西厚德电力技术有限公司、陕西德齐源建设工程有限公司、西安飞龙云兴信息科技有限公司、陕西天网物联科技有限公司、陕西高速星展科技有限公司、西安长亨天信息技术有限公司、陕西云安服信息科技有限公司、西安长荣软信信息工程有限公司、陕西广信新媒体有限责任公司、西安识庐慧图信息科技有限公司、西安乾迈电子科技有限公司、陕西环保产业研究院有限公司、鸾图数字科技(西安)有限公司、陕西鸿铭通机电安装有限公司。不换名/重试/扩大范围，空响应不等于没有证书。

validFlag省略时服务端是否仍有内部默认过滤未独立审计；实际都返回“有效”不证明不存在暂停、撤销或历史证书，不声称已查全所有状态。

## 实际检查与恢复

执行前默认inert实际新增0 SQL/HTTP/model尝试、0文件，并以SQL连接/socket连接/create_connection/DNS四项真实拒绝自检通过；最终短SQLite mode=ro/query_only核对50家name/version、全部原声明及映射ITSS证书相同，关闭只读连接后再次完成四项离线拒绝自检。86份成功raw/body SHA及36条列表-详情字段逐项一致。不是普通联系字段validate_batch，也没有假称该维护函数通过。

逐次HTTP及逐家journal即时持久化，读取和离线中段检查点独立保存。仅写本单元目录与独立证据，不改共享SDD/checkpoint/coverage。私有恢复目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/qualification-q7-itss/`。

- candidates.json SHA256：`4282fc5993d866d501e09073fa6a20d872edb92d949295665cd4c1fb79604f4d`
- journal.json SHA256：`1ad225c5dbc9e3631dcd6a00da6da52ad24ade083fb2034f7334b105b4abd8d1`
- final-receipt.json SHA256：`0b5b54da8edcbf145b9bf5b10294bd0669ff676e10976acb1ac162217abd619d`

首次发现覆盖和实际资料补入均未因本研究增加；36条是待根审核公开证据，14家为本次未知，全部原声明及核实状态保留。
