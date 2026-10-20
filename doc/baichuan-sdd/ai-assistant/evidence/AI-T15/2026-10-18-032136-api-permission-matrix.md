# AI-T15 / AI-AC14 实际 API 逐入口权限矩阵

取样时间：2026-10-18 03:21（北京时间）。本单元只新增隔离测试，不修改业务代码、表结构、前端或服务，不访问所属真实数据库、模型或网络。结论限于以下实际后端入口；不能替代浏览器验收、目标部署验收或完整研究验收。

## 实际检查

新增 `services/business/backend/portal/tests/test_baichuan_api_permissions.py`，SHA256 `b5ebd2c10edc76853c91fd25de2ad2d55cd52d6d9d7289fd802209de8ff0d2ca`。

使用真实 Django ORM、APIRequestFactory 与 URL resolver 调用13条现有路由；禁用账号另走真实 Django Client/session 认证边界。查询和证据为合成夹具，不运行模型。导出夹具经正常 enqueue/claim/process_export 生成真实 XLSX，正向下载读取完整流并核对文件 SHA256。

| 入口组 | 实际路由/能力 | 动态拒绝结果 |
| --- | --- | --- |
| 全局入口 | GET `assistant/config/`、POST `assistant/conversations/`、POST `research/manifests/` | 撤销读权403；禁用账号401。config及新建会话不携带旧对象，正向证明使用当前 owner/scope；研究另需维护权 |
| 会话与输入 | GET `assistant/conversations/{id}/`；POST其 `messages/`、`attachments/` | 跨owner、跨scope和随机不存在ID均404；撤销读权403；禁用账号401 |
| 任务 | GET `assistant/jobs/{id}/`；POST其 `cancel/`、`retry/` | 同上；读同时覆盖查询任务和导出任务，retry使用实际可重试failed任务，排除无效状态偶然拒绝 |
| 结果及来源 | GET `assistant/results/{id}/` | 同上；来源随授权结果内联，正向只返回该快照引用的合成证据 |
| 导出 | POST `assistant/results/{id}/exports/`；GET `assistant/exports/{id}/download/` | 同上；下载目标为实际可下载文件，排除文件不存在偶然拒绝 |
| 维护报告 | GET `research/manifests/{id}/` | 跨owner/scope、不存在、撤销读权或只读账号均404；禁用账号401 |

跨owner对照账号本身也具维护权限，避免研究报告因为缺角色权限而偶然404。跨scope对照仍用原对象的合法owner。逐对象入口均同时对比随机不存在ID，验证相同 `not_found` 响应约定。无读权保留账号active并单独撤销读授权；禁用账号则由真实认证链拒绝，不通过 force_authenticate 绕过认证。

每个拒绝请求前后比较15张目录、资质、人员、会话、消息、附件、任务、任务项、快照、证据、修订、证书、研究清单、研究项与导出表的全部行/列，以及临时storage所有文件路径与SHA256。拒绝审计事件为预期行为，明确不包含在该不变集合。成功只读请求也比较同样保护状态。只读账号可读取自己的结果/来源/下载及创建私人会话，不能创建维护研究或读取维护报告；创建私人会话不改共享企业表。

`socket.create_connection`、`socket.getaddrinfo`、worker模型入口以及研究模型/搜索/正文入口均设为异常守卫并在cleanup确认零调用。测试runner清理继承的PORTAL配置，使用新临时file-SQLite和临时storage，结束后回收。

## 执行记录

```powershell
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan_api_permissions
```

最终 **7 tests / 8.854s / OK / 0 skip**；Django system check无问题。静态AST解析及尾随空白检查通过。存在既有staticfiles目录缺失警告，未影响API权限断言或跳过测试。

首次7项运行耗时8.847s，6组通过、1组错误：只读账号夹具没有维护manifest，但通用路由构造器访问其 `None.pk`，尚未进入该正向请求。仅修正夹具路由在此情形使用已有维护者manifest；原失败日志保留，不视为业务权限缺陷。

私有收据目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/api-permission-matrix/`。

- `receipt.json`：SHA256 `02847bc704f4ca211ecc863728bd4925f975ed26e3f3a37270cca21a14c11829`。
- `targeted-final.log`：SHA256 `af0a417bb4fc209f52d20b140d0d78d6de0ba6fd76e8e373bfbceac1c880e945`。
- `targeted-first.log`：保留首次夹具错误，SHA256 `851ee7206edf012f7809ffa1cda0aa211d07cce34f4e22557b1615bcfdd9ba95`。

## 准确边界与后续

当前13条实际路由中，`assistant/conversations/`仅POST创建，没有GET会话列表；附件只有上传入口，没有附件下载/预览入口；没有独立source接口或export详情接口。会话详情承担消息/附件元数据恢复；sources内联于results；导出状态通过任务读取，文件通过导出下载读取。本测试以真实路由清单断言这些边界，没有为不存在的入口宣称动态权限通过。该路由数断言也使未来新增入口时必须补矩阵。

执行中撤权后的任务终止/租约释放/不发布checkpoint仍引用既有 `test_baichuan_jobs.test_revoked_permission_persists_failed_without_publishing_checkpoint` 的实质断言，本单元不重复运行该测试；最终全回归由主代理统一执行。本单元7项通过不意味着新版本全套已经通过或已被运行服务加载。既有327/328中间回归、旧321回归与实际UI证据分别保留原版本边界，不由此升级。

本单元未发现真实权限缺陷，未修改业务代码。AI-AC14整项状态及其余任务/检查点由主代理结合最终回归和既有撤权证据审阅，本文不修改共享状态。
