# 百川机器人本地交付与数据运维

AI-D39部署前当前范围完成（2026-10-18T21:00:40.390306+08:00）：用户明确尚未到正式部署阶段，本轮未部署。新增Chrome for Testing155.0.8059.84与Firefox157原页面补验：两角色各4视口，另Firefox原生关闭blur能力，共24组视口/6组触屏仿真通过；两浏览器四组角色的原结果恢复、文件选择与移除、既有Excel下载及刷新通过。portal93表+platform6表、18451文件/1131103415B备份与恢复副本哈希一致；两角色密码/绑定/权限/结果/既有Excel及36份附件实际回读通过。0应用源码改动、0新查询/模型/导出生成、0构建/服务重启，163当前前端指纹与全部资料保持。D38的617项/前端16项为输入未变的历史有效检查，本轮不冒充重跑。真机、Safari、物理输入法及新机器整机冷恢复未执行；速度/资料补全继续按用户要求延期，不是当前交付前置项。 [本轮证据](evidence/AI-T17/2026-10-18-d39-predeployment-browser-and-full-restore.md)。

以下保留历史；当前交付状态以D39为准。

AI-D38本地交付收尾完成（2026-10-18T20:29:09.533178+08:00）：47模块617项新回归PASS/322.841s/0skip/87输入；前端16项、TypeScript及助手ESLint通过。Edge双角色1920/1440/768/390共8视口、键盘焦点、可信浏览器组合输入及减少动画通过；支持范围为本机Edge，物理输入法候选窗口、Chrome/Firefox和原生无blur环境未验收。断网中文提示与保留草稿、恢复不自动发送、丢响应同键重提只产生一个任务、观察断流后任务继续、损坏PDF明确失败及原页面关联重试/显式文字替代/刷新恢复通过。修复损坏/加密等内容错误未进入未读附件恢复协议的缺口，基础设施/安全/限额错误仍独立保留。仅备份加载所属portal/worker（2026-10-18T20:24:31.910292+08:00），原前端21632与两网关保持，161其他冻结文件/CSS/布局/入口及原资料保持；93表在线备份与恢复副本全结构/全行摘要一致。速度和资料补全按用户要求延期，远程未操作；并非原SDD全浏览器/整机灾备全部通过。 [本轮证据](evidence/AI-T17/2026-10-18-d38-final-local-handoff.md)。

以下保留历史时点；当前范围以上述D38为准。

任务：AI-T17，本轮AI-D34的本地运维子单元。绑定观测时间：2026-10-18T16:53:40.799644+08:00。本文是可执行的恢复说明与副本演练记录；同轮流式回答、角色组合验收及最终加载由主执行单元继续完成，最终版本须以其回归、加载收据和[检查点](checkpoint.json)重新绑定，不能把本文的观测点当作AI-D34最终交付。

本地入口：[百川库](http://127.0.0.1:13180/departments/product/baichuan)。此环境来自用户原名录，不是找回的历史研究数据库。资料补全已按用户要求暂停；日常检索、附件、追问和重试均不自动补齐。原前端进程保持，前端冻结遵守下述本轮明确例外。

本轮用户已许可为流式回答调整助手的接收逻辑。该许可只覆盖实现增量接收、断流处理及必要的会话状态保护，不扩大到页面布局、样式或其他业务前端。原163项冻结清单继续作为历史基线保留，不能重写清单掩盖差异；最终交付另列获准文件及修改前后SHA，其余文件继续逐项要求与原清单一致。不构建、不重启前端。本文16:53副本演练时163项仍全同，是该时间点的实测结论，不能冒充流式接收改动后的163项全同。

## 版本与运行归属

Git HEAD观测值为`ef1676cd8327d693dab897c45a234ba91413884e`；功能改动未提交，**单独HEAD无法标识当前运行版本**。复现版本至少保留：工作区输入文件SHA256映射、实际测试收据及日志、加载收据中prepared/loaded映射、依赖解释器、数据库迁移状态、所属环境和源表收据。后台使用`--noreload`，磁盘源码更新不等于运行服务已加载。

本次独立生成的版本观测文件记录了HEAD、工作区状态摘要、后端文件映射及其与前次D33加载映射的差异，不保存账号、模型密钥或完整环境变量：`.runtime/baichuan-ai-local/night-acceptance-20261018/d34-local-operations/version-at-observation.json`。同时实施的D34可能改变磁盘文件，因此主执行单元需要在最终加载时重新生成版本映射。

| 对象 | 当前归属核对方法 |
| --- | --- |
| 所属环境 | `.runtime/baichuan-ai-local/environment.json`的kind须为`baichuan_ai_isolated_local_v1`；路径不得经符号链接转向别处 |
| 实际数据库 | `.runtime/baichuan-ai-local/portal.sqlite3`；明确`mode=ro`、`PRAGMA query_only=ON`核查；不靠文件名猜库 |
| 数据来源 | `source-status.json`应为已完成的`local_original_excel`，保留`local_source_only=true`和`historical_enrichment_restored=false`的解释；源表SHA为`220ec53ebe6a87263978f297891107700070d07588a4532b62ba884d64f68f07` |
| 进程 | 从`processes.json`逐一核对PID、创建时间、可执行路径、完整命令；PID相同不代表仍是同一进程 |
| 前端冻结 | `frontend-freeze-20261017.json`原163项清单保留；仅本轮明确获准的助手接收文件可出现已记录差异，其余项SHA须一致；原前端PID21632属于历史加载及本次观测值，之后仍需核对创建时间 |
| 私有凭据 | `accounts.json`、`secrets.json`及模型配置保持原ACL，不打印、不写入公共文档、不提交版本库 |

安全只读状态入口，在项目根目录执行：

```powershell
& '.runtime/company-test/python/Scripts/python.exe' -X utf8 scripts/baichuan/local_dev.py status
```

该命令验证环境与所属进程，不调用真实模型。异常时看所属`portal.log`、`baichuan-worker.log`、`gateway.log`、`model-gateway.log`，先筛选并脱敏；不得把完整日志、token、环境变量输出给外部服务。常规健康端点不应触发模型请求。本子单元没有额外调用HTTP健康、浏览器或模型。

**当前冻结范围内，禁止直接运行`local_dev.py start/stop/migrate/_seed`作为恢复快捷方式。** `stop/start`涉及整个服务组及前端，`start`还会先执行`_seed`；旧[scripts运行说明](../../../scripts/baichuan/README.md)中的全组重启建议不能用于本次冻结交付。仅在主执行单元已有当前源码检查、备份、归属校验和后端加载回执的条件下，按其专用包装器仅处理所属portal/worker，保留frontend/gateway/model-gateway。旧私有`restart_backend_only.py`仍含证书1460的历史断言，不能裸跑；D33包装器已显式绑定当时1622证书及582项回归，新版本应重新绑定，而不是删除断言绕过。

## 在线备份与副本校验

运行中的SQLite使用SQLite Backup API；不得仅复制`portal.sqlite3`而忽略WAL，也不得把备份写回源路径。备份写入全新私有目录，先建立当前Windows SID的独占ACL，路径需位于`.runtime`且无符号链接。备份前保留来源、时间、代码映射和任务状态；存在正在执行的正常任务时，备份是数据库的一致时间点，不能假定它与另一个时刻的计数完全相等。

下面是供后期操作员执行的**新备份示例，本文编写时没有执行此示例**。它只读取所属库并写入新目录，不启动应用，不迁移，不发送网络或模型请求。实际本轮运行见下一节。

```powershell
@'
from pathlib import Path
from datetime import datetime, timezone
import importlib.util, json
root = Path.cwd().resolve()
script = root / 'scripts/baichuan/rehearse_flagoff_backup.py'
spec = importlib.util.spec_from_file_location('backup_only', script)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
runtime = root / '.runtime/baichuan-ai-local'
marker = json.loads((runtime/'environment.json').read_text(encoding='utf-8'))
assert marker['kind'] == 'baichuan_ai_isolated_local_v1'
target = runtime/'manual-backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
helper.private_directory(target)
receipt = helper.backup((runtime/'portal.sqlite3').resolve(strict=True), target/'portal-backup.sqlite3')
(target/'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps({'backup_directory':str(target), 'quick_check':receipt['quick_check'], 'sha256':receipt['sha256']}))
'@ | & '.runtime/company-test/python/Scripts/python.exe' -X utf8 -
```

备份完成后，在副本上执行`PRAGMA quick_check`、`PRAGMA integrity_check`及`PRAGMA foreign_key_check`；前两项应只有`ok`，外键检查为空。以表结构、主键、全表逻辑摘要和计数核对副本；不能仅用文件大小或“能打开”当成功。将备份再复制至不同的全新路径作为恢复工作副本，并重新校验SHA256及上述数据库检查，所有读写路径明确排除主库、试运行库和远程库。副本里可做恢复/开关演练，不能把模型连接、worker或出站网络指向真实服务。

本轮只覆盖portal数据库一致性备份与副本读取。**完整应用灾备还需要分别备份platform数据库、私有附件/导出存储、源表/来源正文/批次收据、代码与依赖、所有权记录及受保护凭据。**平台与portal是两个独立SQLite，不保证跨库同一事务点；需另外定义停写窗口或协调快照。凭据必须用独立受控渠道保管，不能放进公共验收文件。本轮没有实施多库协调备份、完整附件恢复或真实灾难切换，因此不宣称整机灾备已通过。

## 本轮实际副本恢复演练

2026-10-18T16:53:40.799644+08:00实际完成，状态`PASS_SCOPED_BACKUP_COPY_REHEARSAL`：

- 五个进程的PID、创建时间、命令和可执行归属在演练前验证通过；163前端文件前后SHA一致。
- 主库仅通过`mode=ro`及`query_only=ON`读取；SQLite在线备份至新私有目录，再复制为另一恢复工作副本。
- 备份与恢复副本的文件SHA一致；全部93张普通表的结构和逐行逻辑摘要一致；两份副本的quick_check/integrity_check均`ok`，foreign_key_check均0行。
- 主库企业、旧资质、人员、证书、依据与事实修订六张保护表，在演练前、备份及演练后计数与内容摘要均相同。
- 主库恢复覆盖0次，服务重启0次，应用导入/迁移0次，模型0次，浏览器0次，HTTP0次，公开研究0次。

| 核心表 | 此备份实际计数 |
| --- | --- |
| 企业 | 1283 |
| 旧资质 | 1460 |
| 人员 | 0 |
| 证书/观察 | 1622 |
| 依据 | 1987 |
| 事实修订 | 4087 |

以上是本次实际核账，不是把历史1283数字当成当前事实。资料计数不能代替核实程度；1622证书/观察也不代表1622条均独立核实。

| 私有证据 | 绑定信息 |
| --- | --- |
| `.runtime/baichuan-ai-local/night-acceptance-20261018/d34-local-operations/receipt.json` | SHA256 `58450ebf937a663460801fffa2787d14c79d42b58065a4da5e70af276103b35e` |
| 同目录`intent.json` | 运行前范围、只读源路径、所属进程 |
| 同目录`online-backup.sqlite3`、`restored-copy.sqlite3` | 两份独立文件，文件SHA写入receipt；不作为主库替换包 |
| 同目录`backup-inventory.json` | 93表逐表计数/结构/逻辑SHA、完整性和外键结果，不导出企业原文或凭据 |
| 同目录`version-at-observation.json` | 时间绑定的工作区及前次加载映射；SHA由receipt绑定 |
| `.runtime/baichuan-ai-local/d34_operations_rehearsal.py` | 本次一次性执行脚本，拒绝已有输出目录，不能直接重复运行 |

本轮没有重新执行旧的功能开关关闭演练。历史隔离演练工具为`scripts/baichuan/rehearse_flagoff_backup.py --output <全新私有目录>`；它会在**副本**中做手工修改及开关恢复测试，有旧证据不代表本轮新执行。再次使用前仍须核对当前源码、迁移及工具中源表/数量约束，不改断言以迎合结果。

## 数据维护规则

旧资质的可信策略来自用户AI-D28确认，当前所属源表环境显式开启；按真实类别和精确等级确定筛选，不重复请求联网发证依据，也不把旧`PRESENT`退回“缺线上来源”的unknown。该策略不修改旧证书核实状态，不传播到新增公开观察。主体不符、明确冲突、已到期/撤销、指定投标日的未知有效性、未声明等级关系仍按真实结构处理；未知和冲突不能判为满足。电话为空不会把已满足资质的企业删除，输出空值也不编造。

资料补全当前暂停。未来明确恢复数据运维时，优先使用已存在的`scripts/baichuan/apply_reviewed_enrichment.py`及事务服务，不写直接全库UPDATE，不重新导入源表。默认无`--execute`时为inert；执行需完整批次路径与SHA，核对全批企业ID/名称/当前version、来源正文与字段定位、主体和证据，随后独占维护锁、在线备份、逐企业事务/CAS、仅补原空字段、冲突保留、批次幂等修订。已有非空值与人工修改保留。网络与模型在该维护进程禁用，常驻服务事实写入/研究开关不因维护而打开。

维护恢复从原`reviewed-enrichment-<SHA>/state.json`、原批次和原备份恢复，先核对归档SHA及已提交的幂等stamp；不重做成功企业，也不把一个失败企业导致的部分提交描述成全批成功。必须核对当前企业version，冲突先停止该项并保留证据。覆盖分别报告尝试、有效研究、成功补空、字段未知/冲突及独立核实，不把“查过一轮”写为全部补齐。当前不执行上述维护或公开研究。

## 代码回退与数据恢复分开

代码回退先保留当前工作区差异和输入SHA，使用已验证的后端版本；不得对整个仓库执行会回退前端或用户改动的reset/checkout。停止新助手入口开关并不自动停止worker：若确需故障处置，按所属进程身份和现有租约/fence协议处理portal/worker，保留前端及网关，记录在途任务与已提交检查点。关闭开关保留增量表、原会话和修订，不做降迁移、不清表、不重复seed。重新加载需本次当前源码的实质测试与新的加载回执；不能借用D33的582项证明D34新源码。

数据恢复先在副本验证，再确定业务损失窗口和增量合并方案。**禁止将旧整库备份直接覆盖仍有后续人工编辑、会话、任务或新资料的主库。**若仅需撤回配置或错误字段，优先按当前版本和期望原值CAS执行最小修复；保留原值、修订与恢复收据。恢复全库不是代码回退的一部分；真实主库切换、远程生产和试运行库都不在本次副本演练范围。

## 技术限制、费用与故障恢复点

用户已明确放开模型使用，所属query任务的`max_model_calls=null`，继续计量每次真实调用及token；不重新加入历史1次或8次的query总调用预算。原技术控制仍保留：本地每actor+route每分钟30次的准入配置、模型网关并发1、worker有界处理、任务超时、有限失败/等待、防重复请求、权限与fence。30/min是本地配置，不等于上游账户配额已核实，也不是30次总调用额度。实际任务持久化budget/checkpoint才是恢复依据，不把默认常量当成某个已提交任务的实际配置。

| 故障 | 先核对什么 | 可恢复点与边界 |
| --- | --- | --- |
| 收起面板/刷新后结果未见 | 原conversation/job/snapshot ID、原正常登录及权限 | 原对话恢复；不要创建重复查询当健康探测 |
| 限流/忙 | job状态、`checkpoint.model_wait.not_before`、lease/fence、模型日志是否已签发 | 本地尚未发给上游的准入拒绝按有界等待；已经签发但响应不确定，不自动重复模型调用 |
| worker退出 | 所属PID创建时间、任务lease/fence、最后已提交检查点 | 按当前已测试恢复协议接管，旧持有者不能续写；保留失败及原快照 |
| 条件结构不合法 | 业务error_code、文件块来源、严格编译结果 | 不用模型网关success代替业务成功；保留错误，用户显式重试或补充需求 |
| 附件不可读 | 原文件hash、解析/OCR能力与错误 | 保留附件与旧要求；按[交付说明](delivery.md)的明确放弃本轮未读附件协议处理，不静默丢弃条件 |
| 导出失败 | 固定snapshot、字段、权限、原export/job ID | 显式重试仍绑定同快照；不以新查询替代旧结果，不自动补资料 |
| 维护中断 | 原批次SHA、备份SHA、state、逐企业stamp及version | 恢复未提交项；已提交幂等跳过；冲突不覆盖 |
| 归属或来源不符 | 所属环境、实际DB路径、进程身份、源表SHA | 停止该操作并留下路径/错误/恢复点；不碰疑似远程或试运行库 |

接续执行先读[README](README.md)、[进度](progress.md)、[检查点](checkpoint.json)及最新证据，区分“源码已改”“隔离测试通过”“所属后端已加载”“原页面实际通过”。本运维子单元只结清说明与数据库副本完整性演练，未提前宣告流式回答、完整角色/浏览器矩阵、远程部署、全库资料补全或完整灾难切换通过。


## D34最终代码与加载绑定

2026-10-18T17:21:05.165268+08:00：当前版本46模块603项/前端12项/TypeScript/ESLint通过，17:18仅所属后端加载并通过两角色原页面文件、追问、阶段流、恢复与来源完整Excel下载。备份副本演练仍为上文16:53历史时点，不能冒充最终主库备份或完整灾备。源码输入、加载、原前端161保持/2授权例外及最终只读保护收据见[本轮交付证据](evidence/AI-T17/2026-10-18-d34-streaming-role-local-delivery.md)；恢复从[检查点](checkpoint.json)继续，不重跑完成批次。


## AI-D36最新加载绑定（2026-10-18T18:26:16.558700+08:00）

最新所属后台于2026-10-18T18:17:26.873618+08:00备份后加载，版本由`d36-retrieval-optimization/regression-final/receipt.json`的87输入及`load/receipt.json`运行指纹绑定，47模块615项实际PASS；前端仅原接收/测试两例外，其余161及原PID21632保持。最新加载前在线备份为`.runtime/baichuan-ai-local/night-acceptance-20261018/d36-retrieval-optimization/load/before.sqlite3`，SHA256 `57d2a7171aa1363d6034f2362f718e34cce44be246fa0ade183cf9bfd2ee344f`，quick_check实际ok；本轮没有再做全平台/文件/凭据协同恢复或写回源库，前D34的93表副本演练仍为历史时点，不能冒充本次全环境演练。当前`closure.json`记录21个不同查询、3导出、3模型和主库全部旧行保护。原D35内容和D34流式能力保持，资料补全继续延期。后期检索问题优先固定输入/快照并核对字段、来源与输出上限，不重核用户已确认旧资质或执行资料维护写库。不得裸跑历史包装器重启以覆盖本版本；新加载须重新绑定当前源码、实测和备份。


D38最终归档：私有目录`.runtime/baichuan-ai-local/night-acceptance-20261018/d38-local-handoff/operations`下的`online-backup.sqlite3`为本次一致备份，`restored-copy.sqlite3`为实际核账副本；`version.json`绑定当前87测试输入、已加载源码、运行依赖和受控凭据位置，`tested-feature-sources.zip`仅是被测功能源码包。备份与副本逐表完整一致，保留ACL；不复制恢复至主库。本次受控后端加载脚本为`.runtime/baichuan-ai-local/restart_d38.py`，它仅供本次前置条件使用，不能当未来通用重启脚本盲目重跑。未来变更先做新检查、新备份、新版本绑定，不全组start/stop，不重建库。


D39私有恢复交付：`.runtime/baichuan-ai-local/night-acceptance-20261018/d39-predeployment-completion/full-restore/captured-workspace`为捕获包，`restored-workspace`为实际回读副本；`private-file-manifest.json`记录全文件哈希，`database-inventories.json`记录两库全表摘要，`final-receipt.json`及`application-readback-final.json`记录实际通过，原`receipt.json`保留首守卫FAIL。本机所需账号/密钥仅存在此私有目录，不向公共位置复制。副本因验证下载产生审计，不覆盖捕获包。未来恢复必须指定全新目录、核对清单、重定向两库及全部私有存储并阻止出站；不能直接将此包覆盖运行目录或裸跑全组seed/start。冷机依赖安装/系统镜像和正式切换不在此次验收。`release-binding/version.json`及被测源码包绑定当前版本，保留现有617及前端16项原日志，无重复模型健康调用。
