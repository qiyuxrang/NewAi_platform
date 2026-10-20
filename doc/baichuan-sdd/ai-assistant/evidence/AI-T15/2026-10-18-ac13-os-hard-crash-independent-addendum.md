# AI-AC13：OS硬终止恢复独立补充审查

这是[06:49逐句审查](2026-10-18-ac13-ac16-independent-clause-review.md)的新独立附录。旧266输入/10输出、原收据与当时“硬终止尚未执行”的结论原样保留。根随后实际完成的两项隔离测试补齐该项输入；本附录仅核对原始代码、日志、收据及SHA，不重跑测试、不读写数据库、不调用浏览器/模型/HTTP、不改前端或共享验收状态。

根实际执行窗口：2026-10-18 06:50:12.970–06:50:35.146（北京时间），命令为隔离check_backend仅运行`portal.tests.test_baichuan_jobs_process_crash`。原日志为**2项/13.696秒/OK/无跳过**，外层墙时22.175秒。此前415项仍按32模块/215.122秒单列，没有“417项同轮整体通过”的执行证据。

## 两个实际边界

| 场景 | 终止前后及恢复实证 |
| --- | --- |
| 已提交检查点后硬终止 | A已提交`next_item=2`、processed=1、一个完成工作项后报告ready；实际测试worker PID3516，venv launcher PID3408。系统硬终止后进程非零退出15，数据库任务仍running、fence/attempts=1；B自然租约到期后读取同检查点/一个工作项，完成后仍只有一个工作项和一个完成任务。 |
| 外层事务尚未提交时硬终止 | A先持久保存`next_item=1`，再在`leased_job`外层原子事务中写工作项及`next_item=2`，在提交前报告ready并停留。实际worker PID27864，launcher PID29380。系统硬终止后未提交工作项/检查点回滚，持久状态为`next_item=1`、processed=0、工作项0；B读到该边界后只写一次工作项并完成。 |

两例使用真实5秒租约和墙钟等待，没有UPDATE租约时间。B为独立子进程；claim后fence/attempts=2，旧A的heartbeat、save_job检查点、save_item均返回stale_lease；第三执行者不能claim已完成任务，终态租约清空，计数为processed=1。

已读原源代码确认：Windows venv launcher与实际worker PID不同时，先通过本机CIM核对ProcessId、直接ParentProcessId及唯一job UUID/ready路径；随后只对该新测试实际worker调用Windows硬终止。两例实际PID均不同于launcher，因此这一身份校验分支必须执行通过，测试才可能达到日志中的PROCESS_CRASH_PROOF。不是仅终止launcher，也不是Python异常、优雅退出或停止空闲所属worker。

隔离runner清除继承PORTAL配置并新建`.runtime/baichuan-checks`下file SQLite；测试和子进程均校验合成数据库路径、真实企业0、ModelCallLog0。子进程socket/DNS尝试为0；采用现有jobs机制，未调用模型路径。本附录没有独立观察已结束的历史OS进程，而是核对当时实际通过的严格源断言与原始执行日志，不把源代码检查称成再次实测。

## 原失败保留

首轮2项失败，原因是直接断言ready PID等于venv launcher PID，实际Windows多一层子进程；失败在硬终止前。原失败收据、日志和精确首版源码SHA `cf12868b85d8f4702464ef9c1670c39d52ead7a79553eb2effd417d893d0b53e`保留。新源码SHA `eaa12002afaf87541489e73c584a7f1075a6cd52d04b44eefd9797b6010d400e`，新实际收据的3个输入与当前文件相等；jobs生产模块仍为旧415所测的`007fc870...`。本轮只新增测试及私有取证产物，不是生产恢复机制改写。

本独立审查首轮还发现归档差异并保留FAIL：根的`first-attempt-source.py`保存为203处CRLF，实际文件SHA为`e013fe45a2c02d28084454ec759756e3287775abf702434eb2f8f56a72c99a47`，不等首轮执行收据中的历史SHA。只进行CRLF→LF转换后精确等于上述cf12868历史SHA。新审查第二版保留原CRLF档案/收据不改，另存一份明确标为派生恢复的LF副本及换行诊断；不把新计算SHA或转换后的文件冒充未变的原始档案。两场景实际2PASS与此归档问题分开报告。

## 放行建议与限制

本项与前一收据中已核对的原生两角色收起/刷新/断网恢复、当前415的取消/重试/澄清释放租约、重复提交/fence/计数等相组合，**建议根将AI-AC13在既定实现、隔离故障注入及已执行原生UI范围内放行**。此前明确缺失的在途OS硬终止输入现已补齐，无需反复重跑415或真实模型。

此建议不声称在实际所属worker或远程生产上实施在途硬终止，不提升旧原生浏览器收据到当前后端重新端到端执行，也不新增原生双击实测声明。AI-AC16仍沿前一收据的保守本地/隔离回退边界；部署、全库资料完整性及正式T18最终验收保持独立。主状态由根统一更新，旧收据不倒改。

根随后另存`first-attempt-source-exact-LF.py`及`first-source-byte-correction.json`：独立按实际文件字节复核，LF新副本确为历史cf12868 SHA，纠正附录明确旧e013fe CRLF文件与此前错误“文件精确相同”声明。新两个文件追加为本附录输入，原独立FAIL及第二版审查原样保留。

私有目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/ac13-os-crash-independent-addendum-20261018-0658/`。`review.py`为保留的失败版本；`review-v2.py`及`attempt2/receipt.json`、`attempt2/inputs.json`记录第二版实际核账。`freeze.py`核对根追加的二进制副本及纠正附录，并生成`archive-correction-review.json`、`final-inputs.json`和`output-manifest.json`/`freeze-complete.json`。均不导入应用或重跑测试。
