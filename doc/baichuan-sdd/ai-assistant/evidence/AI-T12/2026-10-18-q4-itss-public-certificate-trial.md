# AI-T12 Q4：ITSS 权威公开证书只读试查

冻结时间：2026-10-18 03:45（北京时间）。本单元仅保存可供审核的公开证书证据，主库证书、企业、事实和修订写入均为0，模型调用0，前端/服务/业务源码改动0；不是证书已经入库或全库资质核实完成。

## 公开入口与请求边界

根代理先保存[ITSS获证单位公开表单](https://www.itss.cn/web/itss/c/xxcx/cert)与该页面声明的xwkTools脚本，本单元不重复这两个请求。表单明确 `API=/api/`、`myServer=itss`、`searchSubmit('/web/certificate/','certificate')`。本单元实际读取另外两个原页面声明脚本，zbxTools中的 `searchSubmit → scSearchSubmit` 明确以GET提交表单序列化参数，xwkTools中的 `getMyserver` 返回既有 `myServer`。据此确定公开路由 `/api/itss/web/certificate/`，没有猜测接口或调用登录功能。

每家仅一次原法定全称查询，保持原公开表单默认 `validFlag=有效`、rows10/page1及原字段。每条返回一行，与目标全称精确相同。每家一次实际表单模板声明的详情HTML读取均200，但HTML仅是动态模板，不冒充已渲染的证书正文。根代理随后明确批准边界调整：每家再读取一次实际HTML中 `xwkLoad('itss','/web/certificate/<actual-id>','cert_html')` 所声明的JSON。该公开数据请求由已保存脚本的 `API+t+e` 构造，未猜测路径。原list与HTML全部保留原字节及SHA。

本单元新增实际GET共11：声明JS2、公共列表3、详情HTML3、经明确批准的详情JSON3；根代理此前GET2另计。所有请求标准TLS校验、公共IP检查、无代理、无自动重定向和重试；未遇验证码/登录。CCRC svapp既有超时及Q2验证过期来源未重试。脚本仅为追踪公开路由而读取，没有执行或采用第三方JS实现，不推定代码许可证。

## 实际公开记录

| 精确获证主体 | 证书编号 | 领域/等级 | 获证日期 startDate | 发证日期 getDate | 到期日期 endDate | 公开状态/申请事项 |
| --- | --- | --- | --- | --- | --- | --- |
| 陕西金合信息科技股份有限公司 | ITSS-YW-3-610020230387 | 运行维护/三级 | 2023-03-20 | 2026-01-27 | 2029-03-19 | 有效/再评估 |
| 陕西安科安全生产技术研究所有限公司 | ITSS-YW-3-610020261084 | 运行维护/三级 | 2026-09-20 | 2026-09-20 | 2029-09-19 | 有效/初次申请 |
| 西安市嘉安电子技术有限公司 | ITSS-YW-3-610020240310 | 运行维护/三级 | 2024-03-04 | 2024-03-04 | 2027-03-03 | 有效/监督评估 |

实际详情JSON来源：[陕西金合](https://www.itss.cn/api/itss/web/certificate/b97589d578b84e63b1e0c0ff4f6e1c26)、[陕西安科](https://www.itss.cn/api/itss/web/certificate/202da1eb0e5d440f9aa06fc61a6219a6)、[西安市嘉安](https://www.itss.cn/api/itss/web/certificate/e539eb8a736e402cb70eb8fc32a09129)。公开页面版权主体为中国电子工业标准化技术协会信息技术服务分会。

三条JSON的 `pgjg` 分别为广州赛宝认证中心服务有限公司、北京赛迪认证中心有限公司、陕西赛威信息技术服务有限公司。详情模板标签明确其为“评估机构”，**未将它们填作发证机构**。实际数据没有法人、独立发证机构、标准号及服务范围；相应候选保持未知。`startDate`原标签为“获证日期”，`getDate`为“发证日期”，分别保存，不悄悄互换。默认有效过滤的一条结果不代表其他状态、其他证书或历史记录不存在，也不作工商身份独立核实。

详情JSON原档SHA256：

- 金合：`2ab048d40c28edc4844ba1c7ce76b9ebbcdff073fcb995c2bf18de4a9f29cd33`
- 安科：`4187e442a81bc6d2f0779cd93e42a3ca1b25187713fed8c096cf96f16e7dc01d`
- 嘉安：`257564731cad9a516b19f6902dcb6eab20503bf0ceb3c7f80e23f03b7f12ac6f`

## 原声明保护与只读代码评估

短SQLite `mode=ro`、`query_only`按精确名称核对，金合当前version5，安科和嘉安version1。各自均有原表ITSS三级PRESENT声明，其映射证书仍为unverified，证号与起止日期空白；全部原行保留。

只读检查 `baichuan_facts.py:127–199`：`propose_certificate` 的冲突条件包括“相同证书号”或者“具有legacy_qualification_id且同grade”。因此三条空证号/空日期的原始三级声明也会命中冲突条件，前提是新证据valid且可写。此情形与已有人工明确证号或日期的实质冲突应区分；本单元没有修改core、没有调用该写入函数、没有绕过权限/事实写开关。后续是否建立专门维护路径由根代理决定，不能因此直接覆盖旧声明。

冻结候选 `qualification-q4-itss-candidates.json` SHA256：`daef4013e25b39c73b79c7482ed1ccf587c8027790f6517dbd93342cdcb9be1c`。该文件是研究证据封套，不是现有普通联系字段批次，也未假称通过联系资料维护器的validate_batch。逐项原list、HTML模板、详情JSON、读取意图、SHA、连续全文摘录/字符定位、原声明和只读代码分支评估位于私有 `qualification-q4-itss/` 及同级候选/收据。

首次离线冻结校验发现HTML的CRLF经通用文本读取转换导致摘要比较失败；改为读取已存UTF-8原字节解码后校验，通过后才生成冻结候选，未重新联网、未改原档。业务事实字段、证书状态和匹配满足判定均未由本研究者提升。
