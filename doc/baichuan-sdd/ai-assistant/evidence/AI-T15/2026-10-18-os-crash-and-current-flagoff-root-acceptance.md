# AI-T06/15/17：真实隔离硬终止与当前版本回退子项验收

根结论：按既定验收范围放行 AI-AC13 与 AI-AC16；任务AI-T13/15/16/17仍按剩余整体条件保持IN_PROGRESS，正式AI-T18未启动。既有32模块415项/215.122s/0skip与本次新增2项/13.696s/0skip分列，未运行统一417项。最终只读检查59份原回归输入SHA未变，业务源码仍为05:27已加载版本。本轮新增一个测试模块，未改业务源码或前端。

## AI-AC13

新增 `services/business/backend/portal/tests/test_baichuan_jobs_process_crash.py`：两个实际OS子进程强制终止场景，分别覆盖持久提交后退出和事务中途退出。Windows虚拟环境launcher与实际worker PID不同，核验CIM直接父进程、唯一job和ready路径后只杀隔离合成子进程；自然等待5秒租约，独立进程B恢复检查点，旧fence三入口拒写、单一工作项与完成均通过。事务中途终止还核验SQLite回滚。合成隔离库公司/模型日志0，DNS/socket尝试0。

`.runtime/baichuan-ai-local/night-acceptance-20261018/os-hard-crash-isolated-0652-attempt2/receipt.json` SHA256 `d16e98da2f8622839092f7c9886df7557c5e65af2d2a39e4b8fa117d4ec29be7`

首轮2FAIL原因是测试夹具误认为launcher PID等于真实worker PID，未执行强杀逻辑；修正后实际通过，保留原失败日志。首次归档用文本方式保存导致CRLF，原归档与原换行纠正收据均保留；另外按bytes写入exact-LF副本，并经独立补审核对，不能用LF文本hash冒称CRLF文件hash。

`.runtime/baichuan-ai-local/night-acceptance-20261018/ac13-os-crash-independent-addendum-20261018-0658/freeze-complete.json` SHA256 `5d4aaa4716afd36945eeb4ac98650608be33a8bbb76f8ad10ef8140a2ba925ee`

独立条款初审及补审见[原15条审查](2026-10-18-ac13-ac16-independent-clause-review.md)、[真实终止补审](2026-10-18-ac13-os-hard-crash-independent-addendum.md)。既有两角色原生UI收起/刷新/离线恢复、取消重试、等待输入不占租约、幂等及进度证据与本次实际硬终止互补，不声称强杀了所属在线worker或远程生产。

## AI-AC16

历史worker暂停恢复与当时关闭开关副本证据保留；因5个相关业务源后来变化，本次对当前641字段版本重跑现有备份副本演练。源连接RO/query_only，实际在线备份校验后仅副本操作；66迁移已应用、无待迁移，两角色均列表1283/精确电子二级346/4分页，详情200、人工保存200、旧版本409、助手关闭503，恢复开关后人工改动仍保留。8个受保护原库表行摘要前后完全一致；quick_check/FK通过；网络/模型尝试0、启动worker0。保留增量schema，不用旧全库备份覆盖后续人工改动。

`.runtime/baichuan-ai-local/night-acceptance-20261018/flagoff-current641-0656/parent-receipt.json` SHA256 `1c21b99814a526eb352f025e04b1a0fc2ddae539aef3816be48833cec1c1f595`

`.runtime/baichuan-ai-local/night-acceptance-20261018/flagoff-current641-0656/copy-receipt.json` SHA256 `7233adff6326cf6d5adde88c473661a9c9094e7db00b009e4eeec0bb745ed780`

`.runtime/baichuan-ai-local/night-acceptance-20261018/flagoff-current641-execution.json` SHA256 `c45462078387cc31639ce3bdcdc13913516278fa6b4e1db82e22120adfd75dd1`

实际演练6.5198s/exit0，59份原回归输入再次核对不变。旧迁移/回填/修订回撤保护测试和实际旧页面证据沿用原执行边界。没有对在线库回退、反向迁移、重启或远程部署，不声称有此类验收。

[当前版本独立补审](2026-10-18-ac16-current641-independent-addendum.md)冻结244输入/4输出，核实59源码及163前端指纹、两角色输出和8原库表摘要；审查本身未重跑测试或SQL。演练有1次被阻断的urllib3 IPv6本机bind探测，不能宣称任何socket尝试均为0；出站网络及模型尝试为0。

`.runtime/baichuan-ai-local/night-acceptance-20261018/continuation641-final/receipt.json` SHA256 `c28a66d54bb77cad7a54225460d6c667aa2298f729223b60b84d6f03b69cbe91`：06:58:28实际5所属进程原身份、4HTTP200、前端163及59原回归输入一致；主库模型29/快照28/会话32/session34，本次没有模型健康调用。

尚未通过的完整UI矩阵（含无blur原生loader阻塞）、全库12字段研究和真实发证核实继续单列；不把AC13/16放行外推为这些项目完成。
