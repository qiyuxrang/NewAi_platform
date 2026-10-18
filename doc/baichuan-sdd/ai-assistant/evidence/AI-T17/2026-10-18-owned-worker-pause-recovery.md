# AI-T17：所属worker实际暂停、旧列表及恢复演练

2026-10-18北京时间01:08:15.136–01:08:38.710收据窗口，**PASS（限本单元）**。主执行者完成代码审阅、实际在途验收及无活动任务核账后明确授权执行；演练期间各代理暂停业务写。不是远程生产操作，也不替代完整AI-T17/AI-AC18放行。

## 执行与边界

实际命令：

```powershell
.runtime/company-test/python/Scripts/python.exe .runtime/baichuan-ai-local/rehearse_worker_pause.py --execute
```

脚本SHA256 `a7a217d52686c66a15ffd2120c7faa79921233898416609852699d9e3252425a`，与根代理审阅版本一致。准备阶段9项纯fixture检查通过，0.012秒；默认入口实测不读取文件、不调用helper/SQL/socket/subprocess，0服务动作。真实命令只执行一次、退出0；没有实际失败或第二次恢复启动，不能将fixture中的故障恢复称为实际事故演练。

执行前复用既有所属环境标记、`services.lock`、同命令校验、原Excel及试运行库只读指纹、后端指纹和163个冻结前端指纹。真实SQLite连接均`mode=ro`加`query_only`；各库存检查均确认queued/running任务为0。实际HTTP仅固定本机登录/绑定、旧列表和健康GET；没有外部检索、业务模型调用、助手新消息、迁移、seed、flags改动、前端构建或页面修改。

两角色先完成正常login/link，再建立停用前库存基线，避免把合法登录更新时间误认作维护覆盖；同时保留登录前库存，严格核账允许的认证变化和全部旧行。token/password不写公开证据。

## 唯一停止对象与恢复

停前恢复收据先持久保存；持有旧worker的已校验Windows内核handle，再核对创建时间、可执行文件及完整进程identity，唯一调用TerminateProcess并等待确认退出。01:08:21.877记录旧worker退出，随后原子移除其processes记录。

| 服务 | 原PID→结束PID | 实际保护 |
| --- | --- | --- |
| baichuan-worker | 7600→12540 | 唯一停止/新启动对象；新identity写入processes.json |
| portal | 27260→27260 | 完整记录及内核进程identity保持 |
| frontend | 21632→21632 | 完整identity及163文件SHA保持 |
| gateway | 23540→23540 | 完整记录及identity保持 |
| model-gateway | 16912→16912 | 完整记录及identity保持，仅健康GET |

worker停止后，product、general_manager各一次旧companies GET均HTTP200、total1283、page_size1实际返回1条；每次查询前确认注册表仅余上述4个保留进程。没有把AI候选或核实结论用作旧列表存活指标。

恢复使用旧worker原command、相同cwd和`local.service_environment('baichuan-worker')`重建的既有launcher环境，`CREATE_NO_WINDOW`启动；环境摘要`2f0a53364d6aa0438929baef1323510d356cee7fc7dc244c42dbf54d2d813845`及配置文件SHA在前后保持。本机未安装psutil，本脚本**未读取旧OS进程的完整环境**，不把同launcher/配置验证包装成OS逐变量取证。原flags保持；进程注册表原子更新，没有停止portal或调用整组start/seed。

结束5个进程全部owned；4个健康端点均200：portal18100/health、gateway18080/api/ping、frontend13180/login、modelgateway18412/health。模型健康GET不发推理请求，ModelCallLog20→20。

## 逐行保护与合法认证增量

所有非SQLite内部表按主键记录行hash，并额外对仅允许登录变动的列生成保护hash。portal93表44381个登录前旧行、platform6表43个旧行，**删除0**。登录后基线至最终没有任何旧行修改；只追加两条旧列表审计。

| 保护项 | 登录前→登录后基线→最终 |
| --- | --- |
| 企业 | 1283→1283→1283，所有字段/ID保持 |
| 原资质/增量证书 | 1460/1460，全程逐行保持 |
| Evidence | 1661→1661→1661，原来源/定位保持 |
| FactRevision | 3488→3488→3488，人工/来源链保持 |
| 查询快照 | 19→19→19，全部旧内容保持 |
| 模型调用日志 | 20→20→20 |
| 固定研究项 | 15396→15396→15396；清单及其他研究表保持 |
| Django会话 | 32→34→34；原32行保持，新登录会话2 |
| portal审计 | 3499→3501→3503；登录2、暂停旧列表2 |
| platform审计 | 41→43→43；登录2 |
| portal全部行 | 44381→44385→44387 |
| platform全部行 | 43→45→45 |

登录前后仅2个授权portal用户的last_login、1条LoginAttempt的started_at/count时窗、2个平台用户的portal_session_enc/updated_at允许变化；其余密码、角色、权限、主体映射等受保护列hash相同。登录后至最终旧用户/会话/审计/权限及所有其他旧行均保持。原证书核实标记没有升级，全库研究完成度不因此提高。两库各轮quick_check=ok。

完整新会话ID及认证变动行ID保存在私有`portal-authentication-delta-identifiers.json`，平台对应ID保存在`platform-authentication-delta-identifiers.json`；不在公开文档/聊天复制可用于认证的session key。

## 私有收据与恢复点

目录`.runtime/baichuan-ai-local/night-acceptance-20261018/worker-pause-rehearsal/`，执行前设置当前Windows SID私有ACL。原库存、暂停和结束库存、恢复收据及完整认证ID都在其中，不提交资料原文。

| 文件 | SHA256 |
| --- | --- |
| recovery-receipt.json | 01249c6263f9433e84ae034e25a8a6363397eb0ae9a7f458a68723af455406ee |
| pre-auth-inventory.json | 0e6ea1854386766c224d3feca5a646eeadb5d7654e449f4ca2ab5fe79ed1eef9 |
| baseline-inventory.json | e1d4fbe5bfb6c0949347846e0d56439cb72790a8e836f9c8fef88b16a1862f9e |
| paused-inventory.json / after-inventory.json | 190d5690d6de16e85e291104ca5e7c82bfc700acdcd36f592c06a95451dc814d |
| portal-authentication-delta-identifiers.json | 6ea1d82f775ad24a2f2e93f626d44f7adafe56cd02aa559416b33d97f957885f |
| platform-authentication-delta-identifiers.json | e7a361b6b4d07f36721e91d7f859c04f4004fb5bf5123447b6b2b79d89d2c8d5 |

暂停和结束库存hash完全相同：恢复worker未新增业务行、任务或模型调用。实际进程注册表已更新，新worker正在运行，不留恢复待办；同命令再次执行会因输出目录存在而拒绝覆盖。脚本异常恢复最多启动一次，已发出但未能确认的启动只保留PID/意图并要求核查，避免重复worker；此异常分支仅以准备fixture验证。

本单元仅证明**所属worker暂停后旧列表仍可用、相同launcher恢复、旧数据与其他进程保留**。结合[在线backup副本关开关演练](2026-10-18-flagoff-backup-rehearsal.md)构成保守回退的两个不同子项；没有在真实原库关闭功能开关、回滚代码/数据库或模拟完整故障切换，不因此声称完整真实回退或远程生产部署通过。共享checkpoint/tasks由主执行者统一更新。
