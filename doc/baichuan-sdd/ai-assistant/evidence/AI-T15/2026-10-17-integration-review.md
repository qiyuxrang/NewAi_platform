# AI-T15 编排边界独立审阅（2026-10-17）

范围：`baichuan_assistant_service/api/worker`、`conditions/matching/rules` 与已经验过的 jobs/export 接口。未改 facts/research/runtime；未接触实际企业数据库、远程环境或部署密钥。所有新增夹具均为虚构企业或合成文件。

## 已修复的实际问题

| 问题与影响 | 实施与验证入口 |
| --- | --- |
| 聊天导出先入队再补 `job.message`，改变完整请求哈希；失败后的 HTTP retry 无法通过原请求校验 | 初次 `enqueue_export(..., message=message)` 固定消息关联；HTTP retry → worker → 新文件实际验证 |
| worker 异常处理使用 claim 时旧 checkpoint/result_ref，覆盖已提交研究进度并把已有结果误标 failed | 失败分支在 fenced 短事务内读取当前状态；保留检查点与结果，已有结果记 partial；预期错误及模拟进程异常均测试 |
| 匹配提交未统一核对部署 scope、任务 owner、条件轮次及预算，且全库计算持有写事务 | 匹配前/提交时两次 `leased_job`，计算移出写事务；owner/scope/revision、计算途中取消与预算过期、同版本幂等测试 |
| 后续轮先执行时没有父快照，会静默把 previous_conditions 置空，丢失原条件 | 从父快照或已持久 conditions checkpoint 继承；父仍在运行则 `defer_job` 退回 queued、释放租约并退还尝试次数；claim 跳过未就绪依赖继续独立任务，父完成后原任务自动恢复 |
| 不明确需求产生全库候选，实际没有可执行条件 | 仅对精确“未明确条件”占位谓词且 unresolved 非空的分支进入 awaiting_input；不匹配、不联网、不导出；下一轮可从该父 checkpoint 补充条件。普通未知证据与未支持类别不会触发这一分支 |
| 新条件同时请求 Excel 时只检索而未自动导出 | 文字显式导出意图随不可变 job payload 入队；查询生成新固定快照后用统一 enqueue_export 幂等提交，绑定同条用户消息，限制条数/候选范围；否定导出不提交文件任务 |
| 文件追问保留 must 的纯提示被当成 unresolved，所有满足企业也被降候选 | 仍保留原文件 must，将纯提示移 checkpoint warnings；真正解析警告仍进入 unresolved |
| 今日撤销状态被用于证明历史或未来日期满足 | adapter 要求证据 revocation_as_of（缺省 checked_on）对应查询 as_of，且检查日期不可在未来；今日、历史、未来及明确历史时点证据均验证 |
| 超过200条消息/100附件后恢复接口永久返回最早一段，最新信息丢失 | 返回最新一段并恢复时间顺序，增加 has_older_messages / has_older_attachments 标记；201消息/101附件实际验证 |
| API/XLSX 原文 locator 可带内部采集 job_id、storage_ref、本地路径 | 白名单只发布页码、行列、段落等定位，保留可核对位置；实际 API 返回与打开生成 XLSX 比对。import_ref 私有路径继续隐藏 |
| 畸形 storage key 抛原始 UUID ValueError | 一致返回 not_found；路径及非字符串输入回归 |
| 现有网关不接受 json_object response_format，且真实模型曾返回 must 数组 | 删除不支持的可选参数；SYSTEM 补完整合法 all 对象示例、日期/数组/整数/非null/数字等级编码约束；compile 严格拒绝未知 schema、SQL与伪来源，不放宽模型数据校验 |

## 实测与复查

可复查隔离命令：

```powershell
& .runtime/company-test/python/Scripts/python.exe doc/baichuan-sdd/ai-assistant/evidence/AI-T02/probe_capabilities.py --review-tests
```

运行器不加载部署 `.env`，在临时 SQLite 上从空库迁移至 0046，并在结束后清理；测试包括新增 integration 17 项、assistant 11 项、因本次修改 defer/claim 而回归 jobs 15 项。最终实际结果：**43 tests / 48.383s / OK**，Django system check 无问题，包含两个独立进程对同一临时数据库的重复提交/claim 竞争。`git diff --check` 及六个变更业务模块与新增测试的 `py_compile` 均实际通过。测试环境缺少 `services/business/staticfiles` 产生既有静态目录警告，未将该警告伪装为部署静态资源已准备。

前序审阅的21项实际通过；随后增加用例时先后暴露两处夹具问题（试图原地修改 append-only evidence、缺少 snapshot.result_revision），已改用新证据记录、补齐必填版本。没有绕过或弱化生产模型约束。

SQL/来源注入复查：模型仅提供受限条件 JSON，compile 对字段/操作符/节点/来源引用设白名单与上限；数据库查询走固定 ORM，未发现模型值被拼接为 SQL、Python 或文件路径。证据 adapter 对部署和企业主体作核验；公开结果只读取自己会话及同 scope 的快照。

真实模型能力与隔离缺配置分开记录：AI-T02 的初始隔离环境没有模型/搜索配置，不能将其当成线上不可用结论。local_start 后续复用既有私有模型配置，已报告经修正后的真实文字及合成 DOCX 浏览器链路生成合法快照，并验证硬性 electronic、优先 ITSS、附件 source_refs 与 completed 解析；该代理负责其真实联调证据。本审阅的模型回归使用受控返回值，不能替代真实模型联调，也未宣称真实联网搜索通过。

## 开关及尚存边界

- `BAICHUAN_ASSISTANT_ENABLED=False` 关闭助手新入口；它不是代码/数据库完整回退。旧 `save_company` 编辑 hook 始终写 facts 新表，因此部署本轮代码前必须完成 0046 增量迁移。关闭开关仍保留编辑历史记录能力，不能在未迁移数据库上声称旧编辑完全无依赖。
- `claim_job` 不读取此入口开关，既有任务仍可继续。若希望停掉执行器，需单独停止已部署 worker；没有在本轮修改远程服务。
- 恢复接口返回最近200消息/100附件并明确截断；更旧历史的游标分页未实施。不能把最近一段恢复称为无限完整历史恢复。
- 自动依赖等待不消耗 attempt，但等待仍计入既定墙钟预算；父轮失败且没有持久条件时保留明确错误，不能猜测父条件。有限轮询在 command 的 poll-seconds 范围内休眠，没有后台无限测试进程。
- 后续窄单元已实现文件要求的明确类别取消/全部取消及多轮去重，见同目录 `2026-10-17-file-condition-relaxation.md`；复杂 OR/NOT 的局部改写、来源不明及任意自然语言修改仍保守澄清，不能称已支持所有多轮修改语义。
- 本轮显式组合导出通过“导出”及有限否定/条数表达识别；并未宣称已覆盖任意中文表达。正常新导出仍走统一权限、固定快照与候选显式选择规则。
- 功能开发与隔离行为证据不代表实际数据库已迁移、远程已部署、真实企业已研究或任何真实字段已经核实；这些数量本证据均不作完成宣告。

无新增第三方实现拷贝或依赖。复用本项目现有 Django/模型网关/解析器、openpyxl 3.1.5 与有限任务接口；外部来源和许可证记录沿用 AI-T02/AI-T14 及规则安装证据。
