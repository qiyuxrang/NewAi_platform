# AI-T12 Q8：固定50家 ITSS 公开证书只读研究

冻结时点：2026-10-18T04:06:43.516937+08:00。本单元仅准备可追溯公开记录，**0主库/企业/证书/事实写入、0模型调用、0前端/服务/核心源码改动**。没有调用证书维护函数或提高verified。根代理唯一审核决定后续，不表示证书已核实入库或全库资质完成。

## 固定名单和真实读取边界

原ITSS声明248行、242个不同企业UUID，6家各2行全部保留。排除Q4三家、Q5二十家、Q6五十家、Q7五十家，从剩余119家按UUID升序固定取50家，不扩大范围。manifest保存全部原声明、已有映射证书和版本，SHA256：`adb3878e546fcd32c6618377820ad3e51993981d9764111d9fbe0c78c3eab2bf`。

复用Q4已存[ITSS获证单位公开表单](https://www.itss.cn/web/itss/c/xxcx/cert)、声明JS和详情模板；0新JS/HTML GET，0第三方脚本执行或代码采用，未假设许可证。每家仅一次完整原名查询，原表单itssType=YW，合法未勾选validFlag时不传该参数；详情只取实际列表certificateId及已声明路由，不猜路径。上限每家1列表+2详情JSON，整批150GET；正常TLS、公共IP、无代理/重定向、2MB限额、12秒超时、串行间隔至少1秒、0重试，验证码/登录/429/明确禁止即整批停止、未处理留pending。

实际50列表+35详情JSON=**85GET，其中HTTP200共85**。完成到下一开始间隔最小1.0000432秒，最慢请求0.2594437秒。未展开精确行0，分页未展开企业0，pending企业0。实际URL、intent、raw/body、SHA、时间和公开路由证据保留。

## 字面等级、日期和未知

35家公司取得35条精确主体详情。公开certificateName字面计数：{"三级": 35}；公开状态字面计数：{"有效": 35}。

逐项与原PRESENT声明比较：可比较等级35条，等级差异0条，非1至4等级字面0条。通用要求保留字面、不强映射1至4级，原空等级继续未知；差异如有仅作审核线索，绝不自动修改或推断等级关系。

startDate按已保存官方模板只保留“获证日期”，getDate为“发证日期”，endDate为“到期日期”；不把获证日期推为当前证书valid_from。独立issuer、标准号、specific scope及valid_from继续未知，pgjg仅评估机构不作issuer。公开“有效”不升级verified或推断确定匹配满足。

| 精确主体（实际详情JSON） | 证号 | 公开类别/级别 | 获证日期 | 发证日期 | 到期日期 | 事项 |
| --- | --- | --- | --- | --- | --- | --- |
| [陕西瑞羿思创电子科技有限公司](https://www.itss.cn/api/itss/web/certificate/3951e74b9e1b43429b90d8ce74d4c1f1) | ITSS-YW-3-610020230338 | 三级 | 2023-03-07 | 2026-02-03 | 2029-03-06 | 再评估 |
| [陕西聚合源网络科技有限公司](https://www.itss.cn/api/itss/web/certificate/ceae33f14ffc4bb2aa8ba4c36cd0e49f) | ITSS-YW-3-610020260313 | 三级 | 2026-03-19 | 2026-03-19 | 2029-03-18 | 初次申请 |
| [榆林城投数字城市建设管理有限责任公司](https://www.itss.cn/api/itss/web/certificate/4415e43c401447798f42ec17bdd71542) | ITSS-YW-3-610020220929 | 三级 | 2022-08-12 | 2025-07-07 | 2028-08-11 | 监督评估 |
| [陕西国测院科技发展有限公司](https://www.itss.cn/api/itss/web/certificate/f180b8f719d74f7a953c231085fc64d1) | ITSS-YW-3-610020260276 | 三级 | 2026-03-13 | 2026-03-13 | 2029-03-12 | 初次申请 |
| [榆林数字上郡信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/dc25a5167c2e4a6fa04ece51c56d56c1) | ITSS-YW-3-610020251343 | 三级 | 2025-12-08 | 2025-12-08 | 2028-12-07 | 初次申请 |
| [西安格蒂电力有限公司](https://www.itss.cn/api/itss/web/certificate/e229094b950644e2bf362a94444bc5fd) | ITSS-YW-3-610020231452 | 三级 | 2023-11-01 | 2026-09-03 | 2029-10-31 | 再评估 |
| [安康市高新区圣恩网络工程有限公司](https://www.itss.cn/api/itss/web/certificate/ae580e9ce91f4801b9e4ec69c60ac280) | ITSS-YW-3-610020260642 | 三级 | 2026-06-22 | 2026-06-22 | 2029-06-21 | 初次申请 |
| [陕西中光电信高科技有限公司](https://www.itss.cn/api/itss/web/certificate/fb237381120145b8bf6a5b1c922d5257) | ITSS-YW-3-610020260165 | 三级 | 2026-01-26 | 2026-01-26 | 2029-01-25 | 初次申请 |
| [陕西蓝思宇翔信息科技有限公司](https://www.itss.cn/api/itss/web/certificate/f556a585506443cd99828b3d33b37cf7) | ITSS-YW-3-610020241276 | 三级 | 2024-09-25 | 2024-09-25 | 2027-09-24 | 监督评估 |
| [西安云湾科技有限公司](https://www.itss.cn/api/itss/web/certificate/c9183612236145e6986f565ee8be4836) | ITSS-YW-3-610020261063 | 三级 | 2026-09-14 | 2026-09-14 | 2029-09-13 | 初次申请 |
| [西安平高智慧能源有限公司](https://www.itss.cn/api/itss/web/certificate/9326ba3429d74fe49cf0eac92578f5e6) | ITSS-YW-3-610020250746 | 三级 | 2025-07-07 | 2025-07-07 | 2028-07-06 | 监督评估 |
| [陕西广电智能工程有限公司](https://www.itss.cn/api/itss/web/certificate/05da088c799a4b468a5ebbfecc2b5ac2) | ITSS-YW-3-610020261121 | 三级 | 2026-09-30 | 2026-09-30 | 2029-09-29 | 初次申请 |
| [云上陕西科技运营有限公司](https://www.itss.cn/api/itss/web/certificate/6e65e6a5b22d47fe995d01f3cd83f04a) | ITSS-YW-3-610020241254 | 三级 | 2024-09-25 | 2024-09-25 | 2027-09-24 | 监督评估 |
| [西安乐华云科技有限公司](https://www.itss.cn/api/itss/web/certificate/4cd01f7e2c374d64929d98f104146800) | ITSS-YW-3-610020240171 | 三级 | 2024-01-19 | 2026-09-08 | 2030-01-18 | 再评估 |
| [西安瑞深信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/36b85807f05246a5af14ab77dedaacea) | ITSS-YW-3-610020231815 | 三级 | 2023-12-18 | 2023-12-18 | 2026-12-17 | 监督评估 |
| [西安承翔电子科技有限公司](https://www.itss.cn/api/itss/web/certificate/66928edef2a54272a0df0e789fd1ef3d) | ITSS-YW-3-610020231600 | 三级 | 2023-11-20 | 2026-09-03 | 2029-11-19 | 再评估 |
| [西安冠威信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/6ed4df4c740049eb9d51013e9cafb199) | ITSS-YW-3-610020240925 | 三级 | 2024-07-15 | 2024-07-15 | 2027-07-14 | 监督评估 |
| [陕西尉图实业有限公司](https://www.itss.cn/api/itss/web/certificate/74f668b7e20449ca93575be106f024ea) | ITSS-YW-3-610020231246 | 三级 | 2023-10-10 | 2026-05-14 | 2029-10-09 | 再评估 |
| [延安蓝岛科技有限责任公司](https://www.itss.cn/api/itss/web/certificate/0e208d701ffb47eb8bcbadbdecfde856) | ITSS-YW-3-610020250705 | 三级 | 2025-06-30 | 2025-06-30 | 2028-06-29 | 监督评估 |
| [西安隆盛鑫源信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/6c171cb5a9a54eb8bb1de4bb2df9b9fd) | ITSS-YW-3-610020240568 | 三级 | 2024-04-12 | 2024-04-12 | 2027-04-11 | 监督评估 |
| [陕西省水务集团智能数据有限公司](https://www.itss.cn/api/itss/web/certificate/07925e13ecbe4768a1846563da589634) | ITSS-YW-3-610020250956 | 三级 | 2025-08-19 | 2025-08-19 | 2028-08-18 | 监督评估 |
| [西安禹源水利科技有限公司](https://www.itss.cn/api/itss/web/certificate/47b091d5b88b49d3a741b1e72dce3234) | ITSS-YW-3-610020250064 | 三级 | 2025-01-27 | 2025-01-27 | 2028-01-26 | 监督评估 |
| [陕西青山四纪信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/4ff7a95723a64a1eb0af061db2144624) | ITSS-YW-3-610020250720 | 三级 | 2025-07-04 | 2025-07-04 | 2028-07-03 | 监督评估 |
| [陕西立邦软件有限公司](https://www.itss.cn/api/itss/web/certificate/8640fd9ad53244b2a3d1438ee3ff7e91) | ITSS-YW-3-610020231909 | 三级 | 2023-12-22 | 2023-12-22 | 2026-12-21 | 监督评估 |
| [西安兰特水电测控技术有限责任公司](https://www.itss.cn/api/itss/web/certificate/4f34403518ef438ba5f410864e6c8cb5) | ITSS-YW-3-610020261150 | 三级 | 2026-10-10 | 2026-10-10 | 2029-10-09 | 初次申请 |
| [中国能源建设集团陕西省电力设计院有限公司](https://www.itss.cn/api/itss/web/certificate/414f3a7d9be1417192c9a0fd8d1fe307) | ITSS-YW-3-610020241686 | 三级 | 2024-12-19 | 2024-12-19 | 2027-12-18 | 监督评估 |
| [陕西英联信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/c789f2d21c354a2597c292c483c2cb41) | ITSS-YW-3-610020250509 | 三级 | 2025-05-13 | 2025-05-13 | 2028-05-12 | 监督评估 |
| [陕西有色科技有限公司](https://www.itss.cn/api/itss/web/certificate/5bae97491adc443cab107b0ae5d5f8d4) | ITSS-YW-3-610020251203 | 三级 | 2025-10-31 | 2025-10-31 | 2028-10-30 | 监督评估 |
| [陕西中石地质科技有限公司](https://www.itss.cn/api/itss/web/certificate/f19ff62fee3b4d9892dd34bbfe36a991) | ITSS-YW-3-610020260031 | 三级 | 2026-01-08 | 2026-01-08 | 2029-01-07 | 初次申请 |
| [陕西中交信通网络科技有限公司](https://www.itss.cn/api/itss/web/certificate/ae46bf86ae74495cb5777eeeeeed1a77) | ITSS-YW-3-610020230823 | 三级 | 2023-07-07 | 2026-03-09 | 2029-07-06 | 再评估 |
| [陕西麦浩熙网络科技研发有限公司](https://www.itss.cn/api/itss/web/certificate/6662b7172ac441a3bb9041c5df35159c) | ITSS-YW-3-610020260949 | 三级 | 2026-08-18 | 2026-08-18 | 2029-08-17 | 初次申请 |
| [陕西投资集团创新技术研究院有限公司](https://www.itss.cn/api/itss/web/certificate/459a40b31f7a4247bb2937e23a431c79) | ITSS-YW-3-610020251120 | 三级 | 2025-10-27 | 2025-10-27 | 2028-10-26 | 监督评估 |
| [陕西深铂瑞信息技术服务有限公司](https://www.itss.cn/api/itss/web/certificate/f80b9426b3594bcbb9d95f3d099e703e) | ITSS-YW-3-610020240380 | 三级 | 2024-03-11 | 2024-03-11 | 2027-03-10 | 监督评估 |
| [榆林氢二氧数字能源有限公司](https://www.itss.cn/api/itss/web/certificate/c719440717304f649a04f32d24b8e07e) | ITSS-YW-3-610020251196 | 三级 | 2025-10-31 | 2025-10-31 | 2028-10-30 | 初次申请 |
| [陕西科盈信达工程管理服务有限公司](https://www.itss.cn/api/itss/web/certificate/9b7395ac8e524f9cb6cf0ae681aba9a9) | ITSS-YW-3-610020260691 | 三级 | 2026-06-30 | 2026-06-30 | 2029-06-29 | 初次申请 |

另15家本次列表无精确主体记录，仅保持未知：陕西烽火云集信息科技有限公司、宝鸡市深蓝科工贸有限责任公司、西安辉光日新光电科技有限责任公司、以联科技(西安)有限公司、西安口岸电子科技有限公司、陕西利骏捷信息科技有限公司、陕西祥源电力工程设计有限公司、西安微媒软件有限公司、翼联科技(西安)有限公司、西安青松光电技术有限公司、中航创智技术(西安)有限公司、诺文科智能通风研究院(西安)有限公司、西安敦讯信息技术有限公司、赛思科技(西安)有限公司、西安网力信息技术有限公司。空响应不等于没有证书。其他未取得完整候选的状态：[]。不换名、不重试、不扩大范围。

validFlag省略时服务器是否仍有内部默认过滤未独立审计；公开结果不证明不存在暂停、撤销或历史证书，不声称已查全所有状态。分支、集团严格按精确名称，不转移证书主体。

## 实际检查与恢复

执行前默认inert实际新增0 SQL/HTTP/model尝试、0文件，并以SQL连接/socket连接/create_connection/DNS四项真实拒绝自检通过；最终短SQLite mode=ro/query_only核对50家name/version、全部原声明及映射ITSS证书相同，关闭连接后再次完成四项离线拒绝自检。全部成功raw/body SHA及35条列表-详情字段实际逐项一致。不是普通联系字段validate_batch，不假称该维护函数通过。

逐次HTTP及逐家journal即时持久化。实际检查点：checkpoint-10.json、checkpoint-25-offline-reviewed.json、checkpoint-50.json。仅写本单元目录和独立证据，不改共享SDD/checkpoint/coverage。私有恢复目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/qualification-q8-itss/`。

- candidates.json SHA256：`da9d0e8522c4dd836845244c395bf6c448553ba6472e2a153b5d9a54123834aa`
- journal.json SHA256：`82b07841806bfcb4ebc4b943439075b6f856a7ef0e1f654182097563a947f52f`
- final-receipt.json SHA256：`e8c91f3d01bba5305fed9dfa70992e984cf6c9529d874d47678dc2227da7f7d2`

首次发现覆盖和实际资料补入均未因本研究增加；全部是待根审核公开证据或未知，全部原声明及核实状态保留。
