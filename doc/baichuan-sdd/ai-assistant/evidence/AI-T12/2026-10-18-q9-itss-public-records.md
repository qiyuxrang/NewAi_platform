# AI-T12 Q9：固定50家 ITSS 公开证书只读研究

冻结时点：2026-10-18T04:10:43.174464+08:00。本单元仅准备可追溯公开记录，**0主库/企业/证书/事实写入、0模型调用、0前端/服务/核心源码改动**。没有调用证书维护函数或提高verified。根代理唯一审核决定后续，不表示证书已核实入库或全库资质完成。

## 固定名单和真实读取边界

原ITSS声明248行、242个不同企业UUID，6家各2行全部保留。排除Q4三家、Q5二十家、Q6五十家、Q7五十家、Q8五十家，从剩余69家按UUID升序固定取50家，不扩大范围。manifest保存全部原声明、已有映射证书和版本，SHA256：`802a0e2c8288bf9f2cb45fc1a7afad368fb1d9e4fb5f87b99ae6891aa2b31ba5`。

复用Q4已存[ITSS获证单位公开表单](https://www.itss.cn/web/itss/c/xxcx/cert)、声明JS和详情模板；0新JS/HTML GET，0第三方脚本执行或代码采用，未假设许可证。每家仅一次完整原名查询，原表单itssType=YW，合法未勾选validFlag时不传该参数；详情只取实际列表certificateId及已声明路由，不猜路径。上限每家1列表+2详情JSON，整批150GET；正常TLS、公共IP、无代理/重定向、2MB限额、12秒超时、串行间隔至少1秒、0重试，验证码/登录/429/明确禁止即整批停止、未处理留pending。

实际50列表+30详情JSON=**80GET，其中HTTP200共80**。完成到下一开始间隔最小1.0000630秒，最慢请求0.3080688秒。未展开精确行0，分页未展开企业0，pending企业0。实际URL、intent、raw/body、SHA、时间和公开路由证据保留。

## 字面等级、日期和未知

30家公司取得30条精确主体详情。公开certificateName字面计数：{"三级": 29, "二级": 1}；公开状态字面计数：{"有效": 30}。

逐项与原PRESENT声明比较：可比较等级30条，等级差异0条，非1至4等级字面0条。通用要求保留字面、不强映射1至4级，原空等级继续未知；差异如有仅作审核线索，绝不自动修改或推断等级关系。

startDate按已保存官方模板只保留“获证日期”，getDate为“发证日期”，endDate为“到期日期”；不把获证日期推为当前证书valid_from。独立issuer、标准号、specific scope及valid_from继续未知，pgjg仅评估机构不作issuer。公开“有效”不升级verified或推断确定匹配满足。

| 精确主体（实际详情JSON） | 证号 | 公开类别/级别 | 获证日期 | 发证日期 | 到期日期 | 事项 |
| --- | --- | --- | --- | --- | --- | --- |
| [西安晨翔电子信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/4a21c0228da14c58b6dfa512f0a92294) | ITSS-YW-3-610020230224 | 三级 | 2023-01-29 | 2025-09-19 | 2029-01-28 | 再评估 |
| [陕西汉唐计算机有限责任公司](https://www.itss.cn/api/itss/web/certificate/374e63f2588c4b66bad6b6161e7c9430) | ITSS-YW-3-610020231023 | 三级 | 2023-08-18 | 2026-06-08 | 2029-08-17 | 再评估 |
| [陕西和文化发展中心有限公司](https://www.itss.cn/api/itss/web/certificate/0d0641c1fae941729f65ca95b0211ff0) | ITSS-YW-3-610020231301 | 三级 | 2023-10-10 | 2026-09-10 | 2029-10-09 | 再评估 |
| [国网(西安)环保技术中心有限公司](https://www.itss.cn/api/itss/web/certificate/e071e54f5bf940b0a6af947e4f17b1d8) | ITSS-YW-3-610020251143 | 三级 | 2025-10-27 | 2025-10-27 | 2028-10-26 | 监督评估 |
| [西安数据资产经营有限责任公司](https://www.itss.cn/api/itss/web/certificate/68363396ab454977b722c6ba5d43379b) | ITSS-YW-3-610020260162 | 三级 | 2026-01-26 | 2026-01-26 | 2029-01-25 | 初次申请 |
| [西安交通信息投资营运有限公司](https://www.itss.cn/api/itss/web/certificate/1bda599cefdb45d4b42d298de8b423da) | ITSS-YW-3-610020250288 | 三级 | 2025-03-17 | 2025-03-17 | 2028-03-16 | 监督评估 |
| [陕西煤亮子网络科技有限公司](https://www.itss.cn/api/itss/web/certificate/565a6d44677b4004a01fe0c89cf8aa0d) | ITSS-YW-3-610020251307 | 三级 | 2025-11-24 | 2025-11-24 | 2028-11-23 | 初次申请 |
| [西安尚瑞信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/2ac307025427482b8812cba541ed6b70) | ITSS-YW-2-610020230016 | 二级 | 2023-01-29 | 2025-10-20 | 2029-01-28 | 再评估 |
| [陕西中御鸿联建筑劳务有限公司](https://www.itss.cn/api/itss/web/certificate/80a7bb7240d245cfb4cc72974f35f261) | ITSS-YW-3-610020241185 | 三级 | 2024-09-03 | 2024-09-03 | 2027-09-02 | 监督评估 |
| [陕西金叶莘源信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/fe389afb959441ddb241085b96cf73e0) | ITSS-YW-3-610020260522 | 三级 | 2026-05-19 | 2026-05-19 | 2029-05-18 | 初次申请 |
| [陕西青鸟网络科技有限公司](https://www.itss.cn/api/itss/web/certificate/b2341ae17eb54dcca2df876b1d218397) | ITSS-YW-3-610020230402 | 三级 | 2023-04-06 | 2026-03-12 | 2029-04-05 | 再评估 |
| [陕西智库城市建设有限公司](https://www.itss.cn/api/itss/web/certificate/8f453a7ec8f5412e880dbc96d8a3033d) | ITSS-YW-3-610020231328 | 三级 | 2023-10-13 | 2026-07-02 | 2029-10-12 | 再评估 |
| [西安捷润数码科技有限公司](https://www.itss.cn/api/itss/web/certificate/a8828ee267b641e3995b90effab48f73) | ITSS-YW-3-610020231299 | 三级 | 2023-10-10 | 2026-09-03 | 2029-10-09 | 再评估 |
| [安康大数据运营有限公司](https://www.itss.cn/api/itss/web/certificate/24b759ef4b7b4abfb17c1be4a11da355) | ITSS-YW-3-610020240903 | 三级 | 2024-07-08 | 2024-07-08 | 2027-07-07 | 监督评估 |
| [西安蜜蜂网络科技有限公司](https://www.itss.cn/api/itss/web/certificate/6ded734042d6439a9c54adcec1ae6bf5) | ITSS-YW-3-610020250136 | 三级 | 2025-02-20 | 2025-02-20 | 2028-02-19 | 监督评估 |
| [西安易度数字科技有限公司](https://www.itss.cn/api/itss/web/certificate/daf9f66beecd41bba5449396f77bcdfb) | ITSS-YW-3-610020231929 | 三级 | 2023-12-28 | 2023-12-28 | 2026-12-27 | 监督评估 |
| [陕西英发创联信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/03920054b03c4a58955c92557f8081b4) | ITSS-YW-3-610020230262 | 三级 | 2023-02-27 | 2026-01-30 | 2029-02-26 | 再评估 |
| [陕西通信建设有限公司](https://www.itss.cn/api/itss/web/certificate/b74b130d88e64202b627855a2ec7c5c5) | ITSS-YW-3-610020241677 | 三级 | 2024-12-16 | 2024-12-16 | 2027-12-15 | 监督评估 |
| [西安中科云睿数字科技有限公司](https://www.itss.cn/api/itss/web/certificate/6e7aabb31ea14dcab5cca14fd24e5c22) | ITSS-YW-3-610020261085 | 三级 | 2026-09-20 | 2026-09-20 | 2029-09-19 | 初次申请 |
| [陕西时代云数据科技有限公司](https://www.itss.cn/api/itss/web/certificate/d8c931d53db7409da2d1beb236d1a105) | ITSS-YW-3-610020260788 | 三级 | 2026-07-20 | 2026-07-20 | 2029-07-19 | 初次申请 |
| [西安艾派信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/3de6921f9f254a9f862bb8a5ce3acbfd) | ITSS-YW-3-610020231570 | 三级 | 2023-11-13 | 2026-10-15 | 2029-11-12 | 再评估 |
| [西安中链奇点信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/10ab2f334cf54d5a8df573226d575c84) | ITSS-YW-3-610020261113 | 三级 | 2026-09-30 | 2026-09-30 | 2029-09-29 | 初次申请 |
| [陕西优百信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/0eb7ddd6819a4435b1205ac448211f8e) | ITSS-YW-3-610020241267 | 三级 | 2024-09-25 | 2024-09-25 | 2027-09-24 | 监督评估 |
| [陕西易通人力资源股份有限公司](https://www.itss.cn/api/itss/web/certificate/e3ff4c69529449009387bc6eb2a6973c) | ITSS-YW-3-610020250315 | 三级 | 2025-03-31 | 2025-03-31 | 2028-03-30 | 监督评估 |
| [陕西美和电子科技有限公司](https://www.itss.cn/api/itss/web/certificate/20e103009a90401ba9ccf5f6e631d854) | ITSS-YW-3-610020231839 | 三级 | 2023-12-18 | 2023-12-18 | 2026-12-17 | 监督评估 |
| [陕西中广汇智能信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/da1fc5ea4a184fd4a98c1b31586be183) | ITSS-YW-3-610020260278 | 三级 | 2026-03-13 | 2026-03-13 | 2029-03-12 | 初次申请 |
| [西安兴水信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/d4559ad5b33445fb86ad786cbb2cc828) | ITSS-YW-3-610020230926 | 三级 | 2023-07-31 | 2026-05-19 | 2029-07-30 | 再评估 |
| [宝鸡高新区大数据服务有限公司](https://www.itss.cn/api/itss/web/certificate/3d012bd35bd84281a8a4559fb0154534) | ITSS-YW-3-610020231453 | 三级 | 2023-11-01 | 2026-07-08 | 2029-10-31 | 再评估 |
| [陕西蓝德智慧交通科技有限公司](https://www.itss.cn/api/itss/web/certificate/4d2b5fc6e5b94ec0bd35797cfc697e41) | ITSS-YW-3-610020251506 | 三级 | 2025-12-29 | 2025-12-29 | 2028-12-28 | 初次申请 |
| [陕西一米科技创新有限公司](https://www.itss.cn/api/itss/web/certificate/3ddf2e73fc7644bbace49c9c7fca1995) | ITSS-YW-3-610020251514 | 三级 | 2025-12-29 | 2025-12-29 | 2028-12-28 | 初次申请 |

另20家本次列表无精确主体记录，仅保持未知：陕西西煤云商信息科技有限公司、陕西沣西科创发展有限公司、西安峰创嘉业网络科技有限公司、西部运维(西安)科技集团有限公司、陕西远洋科技实业有限责任公司、陕西长安计算科技有限公司、博亚盛亿(西安)科技有限公司、安康市九州智能科技有限公司、西安安柏电气工程有限责任公司、陕西安华讯科技有限公司、西安公路勘察设计院有限公司、陕西麦邦感知人工智能技术有限公司、西安正亨工程科技有限公司、西安国际医学中心有限公司、西安中霖信息科技有限公司、西安天智数字信息科技有限公司、陕西海泽天成信息科技有限公司、榆林科大高新能源研究院有限公司、联通(陕西)产业互联网有限公司、陕西中昊智能科技有限公司。空响应不等于没有证书。其他未取得完整候选的状态：[]。不换名、不重试、不扩大范围。

validFlag省略时服务器是否仍有内部默认过滤未独立审计；公开结果不证明不存在暂停、撤销或历史证书，不声称已查全所有状态。分支、集团严格按精确名称，不转移证书主体。

## 实际检查与恢复

执行前默认inert实际新增0 SQL/HTTP/model尝试、0文件，并以SQL连接/socket连接/create_connection/DNS四项真实拒绝自检通过；最终短SQLite mode=ro/query_only核对50家name/version、全部原声明及映射ITSS证书相同，关闭连接后再次完成四项离线拒绝自检。全部成功raw/body SHA及30条列表-详情字段实际逐项一致。不是普通联系字段validate_batch，不假称该维护函数通过。

逐次HTTP及逐家journal即时持久化。实际检查点：checkpoint-10.json、checkpoint-25-offline-reviewed.json、checkpoint-25.json。仅写本单元目录和独立证据，不改共享SDD/checkpoint/coverage。私有恢复目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/qualification-q9-itss/`。

- candidates.json SHA256：`723735a982f378d8db23eaab3efec0a5db332cd2f9bec73ee7ebca131dd20054`
- journal.json SHA256：`bc153caaa66be77eee9fa4ebdd8bcb4444a309d5481dc6a7785c11ab0c024a1b`
- final-receipt.json SHA256：`7a44004e5c238bfeaa79c7925f84b737e5fcb47a133799c5fee84c3c76c47977`

首次发现覆盖和实际资料补入均未因本研究增加；全部是待根审核公开证据或未知，全部原声明及核实状态保留。
