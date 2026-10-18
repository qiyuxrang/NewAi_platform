# AI-T12 Q10：最后19家 ITSS 公开证书只读研究

冻结时点：2026-10-18T04:13:24.606459+08:00。本单元仅准备可追溯公开记录，**0主库/企业/证书/事实写入、0模型调用、0前端/服务/核心源码改动**。没有调用证书维护函数或提高verified。根代理唯一审核决定后续，不表示证书已核实入库或全库资质完成。

## 固定名单和真实读取边界

原ITSS声明248行、242个不同企业UUID，6家各2行全部保留。排除Q4三家、Q5二十家、Q6至Q9各五十家，固定最后19家UUID有序补集；已断言与既有223家互斥、并集恰为原242家，不扩大至没有原ITSS声明的企业。manifest保存原242 ID全集、全部目标原声明、已有映射证书和版本，SHA256：`8279eb710374f57f6f4edc48325e808b5cdfb06206cef414f0faa60dc7053f42`。

复用Q4已存[ITSS获证单位公开表单](https://www.itss.cn/web/itss/c/xxcx/cert)、声明JS和详情模板；0新JS/HTML GET，0第三方脚本执行或代码采用，未假设许可证。每家仅一次完整原名查询，原表单itssType=YW，合法未勾选validFlag时不传该参数；详情只取实际列表certificateId及已声明路由，不猜路径。上限每家1列表+2详情JSON，整批57GET；正常TLS、公共IP、无代理/重定向、2MB限额、12秒超时、串行间隔至少1秒、0重试，验证码/登录/429/明确禁止即整批停止、未处理留pending。

实际19列表+15详情JSON=**34GET，其中HTTP200共34**。完成到下一开始间隔最小1.0001076秒，最慢请求0.2479530秒。未展开精确行0，分页未展开企业0，pending企业0。实际URL、intent、raw/body、SHA、时间和公开路由证据保留。

## 字面等级、日期和未知

15家公司取得15条精确主体详情。公开certificateName字面计数：{"三级": 15}；公开状态字面计数：{"有效": 15}。

逐项与原PRESENT声明比较：可比较等级15条，等级差异0条，非1至4等级字面0条。通用要求保留字面、不强映射1至4级，原空等级继续未知；差异如有仅作审核线索，绝不自动修改或推断等级关系。

startDate按已保存官方模板只保留“获证日期”，getDate为“发证日期”，endDate为“到期日期”；不把获证日期推为当前证书valid_from。独立issuer、标准号、specific scope及valid_from继续未知，pgjg仅评估机构不作issuer。公开“有效”不升级verified或推断确定匹配满足。

| 精确主体（实际详情JSON） | 证号 | 公开类别/级别 | 获证日期 | 发证日期 | 到期日期 | 事项 |
| --- | --- | --- | --- | --- | --- | --- |
| [西安源捷科技有限公司](https://www.itss.cn/api/itss/web/certificate/5f95b90af25841eabdd66ae92f52bff4) | ITSS-YW-3-610020240408 | 三级 | 2024-03-19 | 2024-03-19 | 2027-03-18 | 监督评估 |
| [渭南市数字经济产业发展有限公司](https://www.itss.cn/api/itss/web/certificate/36da6bf809384e3497848b334af5c113) | ITSS-YW-3-610020261004 | 三级 | 2026-08-25 | 2026-08-25 | 2029-08-24 | 初次申请 |
| [西安星讯智能通信科技有限公司](https://www.itss.cn/api/itss/web/certificate/0adae2af798a476bbe4c9c6abda9ab83) | ITSS-YW-3-610020260654 | 三级 | 2026-06-24 | 2026-06-24 | 2029-06-23 | 初次申请 |
| [陕西鑫旺智能工程有限公司](https://www.itss.cn/api/itss/web/certificate/419f17eaa59c4a4a9f63873e4f62dbbc) | ITSS-YW-3-610020241182 | 三级 | 2024-09-03 | 2024-09-03 | 2027-09-02 | 监督评估 |
| [陕西秦云智能信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/e02bf6be6ab24aa88bfcf60641d8a867) | ITSS-YW-3-610020251033 | 三级 | 2025-09-16 | 2025-09-16 | 2028-09-15 | 监督评估 |
| [西安悦泰科技有限责任公司](https://www.itss.cn/api/itss/web/certificate/1cdd3a3041a34f61ae18bd9b5eb6f012) | ITSS-YW-3-610020250648 | 三级 | 2025-06-16 | 2025-06-16 | 2028-06-15 | 监督评估 |
| [陕西银兴智能科技股份有限公司](https://www.itss.cn/api/itss/web/certificate/94169120da024ed0b990dd278e90298b) | ITSS-YW-3-610020240536 | 三级 | 2024-04-12 | 2024-04-12 | 2027-04-11 | 监督评估 |
| [陕西浩云微码信息技术有限公司](https://www.itss.cn/api/itss/web/certificate/dee4487589ec4bce837d9a167b287aca) | ITSS-YW-3-610020250655 | 三级 | 2025-06-16 | 2025-06-16 | 2028-06-15 | 监督评估 |
| [陕西匠盟盟实业有限公司](https://www.itss.cn/api/itss/web/certificate/dca15c11ad214c21b39842c1ca940220) | ITSS-YW-3-610020230365 | 三级 | 2023-03-20 | 2026-03-04 | 2029-03-19 | 再评估 |
| [西安黄河环境信息工程有限公司](https://www.itss.cn/api/itss/web/certificate/496b4e81ce09495b9f8a4155d9cc20b4) | ITSS-YW-3-610020240584 | 三级 | 2024-04-26 | 2024-04-26 | 2027-04-25 | 监督评估 |
| [西安亚北时代科技有限公司](https://www.itss.cn/api/itss/web/certificate/7509e1a5a159419b909fa1ec703899e0) | ITSS-YW-3-610020260239 | 三级 | 2026-02-06 | 2026-02-06 | 2029-02-05 | 初次申请 |
| [陕西钢铁集团禹龙科技服务有限公司](https://www.itss.cn/api/itss/web/certificate/8985130f7baf41fd85b3da246cb53f62) | ITSS-YW-3-610020240934 | 三级 | 2024-07-16 | 2024-07-16 | 2027-07-15 | 监督评估 |
| [陕西益利德软件科技有限公司](https://www.itss.cn/api/itss/web/certificate/0839e941a7fa48d59343af9fd232be96) | ITSS-YW-3-610020260494 | 三级 | 2026-04-20 | 2026-04-20 | 2029-04-19 | 初次申请 |
| [西安韵通网络科技有限公司](https://www.itss.cn/api/itss/web/certificate/52e47bf0225f489494ee858c55839b4e) | ITSS-YW-3-610020231036 | 三级 | 2023-08-18 | 2026-04-23 | 2029-08-17 | 再评估 |
| [西安中奥数智科技有限公司](https://www.itss.cn/api/itss/web/certificate/adc4c44b6924449ba1befa22249dc058) | ITSS-YW-3-610020251026 | 三级 | 2025-09-16 | 2025-09-16 | 2028-09-15 | 监督评估 |

另4家本次列表无精确主体记录，仅保持未知：陕西交通科技有限公司、铁科经纬(西安)信息技术有限公司、陕西北控数智建设工程有限公司、陕西天石云网智慧建筑科技有限公司。空响应不等于没有证书。其他未取得完整候选的状态：[]。不换名、不重试、不扩大范围。

validFlag省略时服务器是否仍有内部默认过滤未独立审计；公开结果不证明不存在暂停、撤销或历史证书，不声称已查全所有状态。分支、集团严格按精确名称，不转移证书主体。

## 实际检查与恢复

执行前默认inert实际新增0 SQL/HTTP/model尝试、0文件，并以SQL连接/socket连接/create_connection/DNS四项真实拒绝自检通过；最终短SQLite mode=ro/query_only核对19家name/version、全部原声明及映射ITSS证书相同，关闭连接后再次完成四项离线拒绝自检。全部成功raw/body SHA及15条列表-详情字段实际逐项一致。不是普通联系字段validate_batch，不假称该维护函数通过。

逐次HTTP及逐家journal即时持久化。实际检查点：checkpoint-10-offline-reviewed.json、checkpoint-10.json、checkpoint-19.json。仅写本单元目录和独立证据，不改共享SDD/checkpoint/coverage。私有恢复目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/qualification-q10-itss/`。

- candidates.json SHA256：`da8144407b8bc3e09a712a9d73cd71b3d3f89e47d8bc2600970341332a3f13ce`
- journal.json SHA256：`25bc8503ca5bad85855e58f29c5a86b6b756716797683233e395204851682af1`
- final-receipt.json SHA256：`8c6125740a6682198b5ccdb048149f49b735b9582aaffafbf34a1809b0d5a444`

首次发现覆盖和实际资料补入均未因本研究增加；全部是待根审核公开证据或未知，全部原声明及核实状态保留。
