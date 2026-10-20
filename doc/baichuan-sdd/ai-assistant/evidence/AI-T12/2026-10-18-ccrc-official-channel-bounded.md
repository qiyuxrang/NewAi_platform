# AI-T12：唯一 CCRC 原声明与官方查询通道有界核查

时间：2026-10-18 05:16（北京时间）。仅只读研究；企业证书查询 **NOT_RUN / unknown**，零新增证书候选，未生成可执行空批次。

## 固定原声明

当前只读企业 ID `80858cad-f34f-5914-a3f0-7d004da1fc08`，名称“中国联通榆林市分公司”，version 1。唯一 CCRC 原 CompanyQualification ID `2e5543f7-3707-5942-9bbb-762933ce4d66`，类别原文“CCRC 信息系统安全集成服务”，等级全文“信息系统安全集成二级/安全运维二级/风险评估二级/应急处理三级”。保留原表 `0-总表` 第 3 行与 `5-CCRC信息安全服务` 第 4 行的完整 source 字段。

既有一条 grade 2 的 unverified 结构化导入投影，证号、有效起始和截止均空；企业关联两条 legacy_import 来源。投影的 bidder 标签不代替实际公开证书主体证明。四个方向不能当作一张已确认的证书，不能借母公司证书补分公司，也不把该原表名称自行改为推断的完整注册名称。

## 实际公开路径

1. [中心官网](https://www.isccc.gov.cn/) 实际 GET 200，正文 SHA256 `b329ee2fab3f9cd43d60a1760c0a3681c9a862ed960f2f712b7da48581efc6aa`。页面的“信息安全服务资质认证证书查询”链接明确为 `/sy/tz/index.htm?xxaq`，与产品、体系、人员认证查询分开。
2. [该公开中转页](https://www.isccc.gov.cn/sy/tz/index.htm?xxaq) 实际 GET 200，正文 SHA256 `822b095b906cb767776c453dbcdf25762ef35fdb2c8e2a590a4c9ca3097b884d`。其 `xxaq` 分支原字面跳转 `https://svapp.isccc.gov.cn/CertSearch_FW.aspx`；保留完整 HTML、raw 字节与精确字符定位，没有猜测接口。
3. 该目标 URL 恰为 Q4 已记录超时的相同通道。本单元经根代理确认不重试，未请求其 UI、未提交企业查询，也未借独立电子证书验签通道绕过。没有观察到本轮目标 UI 的验证码或登录状态，不能凭未请求的页面宣称无验证码或公开可用。

两页的查询链接均无可识别发布日期，只记录实际读取时间。网页搜索共 3 次，其中公司精确名称官方限定搜索未命中；未命中不说明没有证书。官方直接 GET 共 2 次、各 12 秒上限、零重试、零自动重定向，未越过任何访问限制。未采用第三方代码，无第三方代码许可证采用；官网内容仅作为原文证据保留。

## 收据与边界

私有目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/qualification-ccrc-channel-20261018-0515/`。`inventory.json` 保留完整原声明、当前证书与来源；`request-history.json`、`get-1/2.raw`、`get-1/2.html` 保留实际请求原件；`final-receipt.json` 和 `artifact-index.json` 冻结结果与 SHA。

只读数据库入口显式 `mode=ro` 与 `PRAGMA query_only=ON`，不加载业务 application。零业务库写入、零模型调用、零 core/test/前端/服务/共享 SDD 改动。issuer、证号、日期、标准、范围及当前有效/暂停/撤销状态全部未知，不能从机构介绍、原表或同集团记录推定。本次不增加 ITSS/CS 覆盖，也不宣称 CCRC 实际证书核验完成。
