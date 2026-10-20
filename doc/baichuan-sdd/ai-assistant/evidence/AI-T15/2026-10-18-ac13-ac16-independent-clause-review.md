# AI-AC13 / AI-AC16独立逐句核账

实际审查时间：2026-10-18 06:49:20（北京时间）。只读证据审查；没有重新运行415项、浏览器、模型、HTTP、SQL或服务操作，没有修改前端、业务源码、任务或共享检查点。主验收状态由根执行者依据本证据和后续实际结果统一决定。

结论：AI-AC13的其他条款已有对应实证，本审查时仍缺“有持久检查点的在途进程被OS硬终止，租约自然过期后由新进程恢复”的直接执行证据。根执行者已另行准备隔离实测；没有提前给该项通过。AI-AC16可建议在既定“隔离迁移/回填、保守所属本地回退”边界放行，不把它扩大成整套代码/数据库真实切换或远程部署通过。

## 指纹与适用版本

已实际重算[415项回归](2026-10-18-final415-and-stage-status.md)收据和日志：32模块、415项、215.122秒、OK，无skip记录；59个记录输入的当前SHA全部相等。日志为整体执行结果，未伪称存在逐方法verbose日志；下表方法定位来自同批受指纹保护的测试源码、命令中完整模块及无跳过执行。

冻结前端163文件均保持原SHA。旧原生浏览器结果绑定当时真实加载版本；产品断网绑定03:59加载收据，总经理断网绑定公开证书维护后加载收据，未称这些旧执行重新跑在当前415后端。旧worker暂停时后端指纹中assistant_api、exports、facts、matching、research_runtime五文件现已不同；legacy API、jobs、assistant service/models保持相同，现有改动由本轮415当前指纹测试另证。历史版本差异逐文件保存在私有JSON，未以旧版本证据冒充新版本完整端到端重跑。

## AI-AC13逐句对应

| 条款/输入 | 已执行证据与范围 |
| --- | --- |
| 收起、刷新；关闭不取消、可恢复 | 产品角色、总经理文字及总经理文件原生202/queued后收起，原列表仍可搜索，后台completed，再原上下文刷新同cid/jid/sid。隔离助手读取接口逐次所有者/scope恢复检查也在415中通过。 |
| 断网 | [产品原生断网](../AI-T13/2026-10-18-040619-native-offline-reconnect.md)、[总经理原生断网](../AI-T13/2026-10-18-gm-native-offline-and-public-certificate-readback.md)均实际passed：queued后断网刷新真实ERR_INTERNET_DISCONNECTED、独立服务端轮询completed、联网后原上下文同结果恢复。无cid/存储注入、无重新提交。总经理此项已执行，旧矩阵NOT_RUN不能继续代表最新状态。断网时无应用壳可用不是在线恢复失败。 |
| 工作进程崩溃 | `test_unexpected_failure_keeps_partial_result_and_raises_for_diagnostics`实际注入RuntimeError，检查已提交partial/checkpoint；`test_crash_reclaims_checkpoint_fence_and_rejects_all_old_writes`直接把租约写成过去时间后恢复。两者在415中通过，但没有实际OS硬终止在途进程。真实worker暂停单元开始时queued/running为0，也不能替代此输入。 |
| 租约过期、旧执行者继续 | jobs的过期未回收拒写、回收后fence递增，旧worker heartbeat/save_job/save_item拒绝均通过；事务内工作项与checkpoint异常同时回滚有测试。自然过期后的OS进程交接仍由上一行后续单元独立举证。 |
| 双击发送、幂等无重复 | 助手同request返回同job且不同payload冲突；线程和独立进程重复提交/竞争claim只建/认领一次，均在415中通过。前端同步sendingRef和丢失确认后复用原request的现有测试作为实现/历史补充。本次没有实际原生双击，不能称做过；后端重复请求结果要求已有实测。 |
| 取消、重试，取消确定终态 | queued/running/awaiting_input取消后cancelled、租约释放、旧执行者拒写、重复取消不变；匹配过程中取消不发布结果；实际worker导出失败→HTTP retry→新文件；独立研究retry保留已完成进度且不重调完成项，均在415中通过。 |
| 等待澄清不占工作租约 | jobs明确awaiting_input释放owner/expires；歧义无研究/导出再恢复、OR/NOT范围澄清及未匹配文件取消均有415断言。 |
| 超时、部分完成和检查点 | 时长/尝试预算达到终态；已提交checkpoint、result_ref和真实counts在预期/意外错误后保留；空manifest不无限running。 |
| 进度不随意报百分比 | 研究工作项/字段进度同事务，retry保留计数；现有前端9项执行证据包含countSummary只接受定义数字计数、拒绝字符串100%；原生收据保留queued/planning/matching/completed真实步骤。本次只核对旧执行和现冻结源码，未重新运行前端测试或声称总体P95。 |
| 后续细化：显式取消文件要求 | 部分取消保留其他要求及旧快照、全部取消后无条件等待输入、OR/NOT不猜、附件或否定句不构成放宽授权、重复多轮不无限嵌套，相关模块已纳入415。 |

最小尚缺输入是一个新的合成file SQLite：A进程claim短租约并提交检查点/工作项后报ready；父进程硬终止并确认退出；等待真实租约到期；B进程恢复同任务、保留检查点、递增fence、拒旧owner/fence的三种写入并唯一完成。不得用UPDATE租约时间、停止空闲所属worker、真实模型或改前端代替。本审查不实施该单元，也不提前计入其结果。

## AI-AC16逐句对应

| 条款/输入 | 已执行证据与范围 |
| --- | --- |
| 隔离迁移/回填，保ID/人工字段/来源 | 415包含0045→0046增量迁移与新表为空时反迁、逐字段保存企业/资质/人员；显式旧声明映射、重复0新增、权限/版本门禁、原来源和旧修订保存。新事实后反迁不是安全方案。 |
| 旧API与编辑快照，关闭所有新开关 | [独立备份副本演练](../AI-T17/2026-10-18-flagoff-backup-rehearsal.md)当前helper SHA与当时收据一致，原before和结束working SQLite文件SHA本次实际重算相等；关闭5开关、0待迁移、两角色旧列表1283、精确二级346逐ID对照、详情/人工PUT200、旧版本409、新会话503。实际调用旧API函数，不是mock响应或原生页面关开关。 |
| 原页面/精确筛选，故障不阻断旧库 | 副本关开关时旧列表/详情/编辑可用；[所属worker暂停恢复](../AI-T17/2026-10-18-owned-worker-pause-recovery.md)实际停止后两角色旧列表200/1283，再启动恢复5所属进程/4health；原生收起时原列表可操作。各自范围独立，不声称暂停时同时实测全部页面或真实flags切换。 |
| 演练回退，不丢后续人工修改 | plan第10节定义关新入口/写入、停新任务、保留表与已写资料，必要时版本化回撤。本轮副本人工保存后恢复助手开关，后写值仍保留；415的`test_revert_one_field_retains_history_and_rejects_later_manual_changes`实际回撤一字段并对后续人工版本拒绝覆盖。结合实际worker停启构成这一保守本地回退方案的独立子项；没有声称live同轮整套代码/数据库切换。不能为补验收而恢复旧整库或删新增表。 |
| 旧声明补链细化 | 415包含legacy_evidence全模块：原文/hash/定位严格一致、权限/版本拒绝、已有引用/修订/旧快照不变、未核实不升级、重复新增0；实际原1460补链证据保留。 |

没有将上述仍未执行的OS在途硬终止、原生双击或真实复合切换笼统称作“UI未完成”，也没有把可选整库/代码downgrade新增为交付要求。AC16建议限于规格明确的隔离与保守回退边界；AC18实际部署、AC19全库资料和正式T18最终核账独立保留。

## 私有收据

目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/ac13-ac16-readonly-clause-review-20261018-0700/`。`review.py`首次执行通过；`clauses.json`逐句保存测试方法/源码行号/指纹，`receipt.json`保存建议和版本限制；`historical-runtime-version-comparison.json`记录历史差异；`minimal-unexecuted-inputs.json`限定下一最小动作。`inputs.json`实际266个只读输入；本单元封存附录另核对补链测试方法与所有输入/输出指纹。过宽工具输出截断和PowerShell下rg通配路径报错123已记入收据，随后精确读取成功，没有把未读到的内容当作通过。
