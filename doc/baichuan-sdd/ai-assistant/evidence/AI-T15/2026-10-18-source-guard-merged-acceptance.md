# AI-T08 / AI-T09 / AI-T15：来源门禁合并与真实表格复验

时间：2026-10-18 00:58（北京时间）。HEAD `ef1676cd8327d693dab897c45a234ba91413884e`，未提交本地工作区。用户原名录所属本地1283家库；没有远程生产操作或前端改动。

## 最终检查与加载

对所有 `portal.tests.test_baichuan*` 模块执行 `scripts/baichuan/check_backend.py`，每次使用新建隔离文件SQLite，清除继承的PORTAL配置。第一次完整回归321项、170.856秒，1项FAIL：旧查询研究策略样例只提供根级附件引用，被新增逐谓词来源门禁拦截。原失败日志保留。

修正该合法正例，让其硬谓词引用实际解析的附件b1，并断言新快照保留同一引用；没有放宽业务门禁。第二次完整回归 **321项PASS、170.276秒、0跳过**。既有109项来源/附件专项与321项重叠，不相加。

私有日志：

- `night-acceptance-20261017/combined-backend-source-guard-final.log`：原FAIL。
- `night-acceptance-20261017/combined-backend-source-guard-r2.log`：最终PASS。

00:55:50.313463仅重载所属portal和baichuan-worker。4项HTTP健康200、5个所属进程；前端PID21632和163个冻结指纹、两个网关进程均保留。加载前后后端源码指纹一致。所有查询、快照、资料、来源原件和原试运行库均保持，0模型/导入/迁移/前端构建。私有 `final-restart-receipt.json` 记录实际加载版本。

## 来源保护及实际复验

文件硬要求缺逐项来源时进入等待输入，不匹配、不导出；模型可用真实当前消息引用表达文字条件，文件条件须定位到实际附件。旧文件guard在合并后重新检查，文字追问、新文件和旧checkpoint恢复不能绕过来源门禁；原快照不改写。门禁检查归属与完整性，不能证明引用文本的真实性。

新固定请求ID只执行一次表格DOCX复验，**1次模型调用、0自动重试、0研究调用**，模型日志19：4779ms，2271输入/465输出token。

- 电子与智能化硬条件定位表1行2；精确二级，投标人主体。
- ITSS评分优先项定位表1行3，不升级为硬条件。
- CCRC硬条件定位表1行4；制造商主体，精确二级。
- 个人CISP无法覆盖的内容保留unresolved。
- 完整1283明细行：candidate1283、confirmed0、excluded0，没有将原未核实声明判为满足。

新快照 `7580e464-1601-43f8-abab-70b8691904c2` 的condition_tree/results/counts/fact_cutoff_at四字段SHA-256为 `a26887e89cdad8deaea2b7e3302c2d9c1d147067b11e7ec32e6983eb7e2269dc`。

私有 `table-source-retest-20261018/receipt.json` SHA-256 `b3b640f8e582da70e538a219e51b3ac4b7784e1490289f15eefb586a15bfcd1e`；后审 `post-readonly-receipt.json` SHA-256 `873cd13ee1ad0f1e17c0203ad64c2081b5274c768e4eaaae8613cdba3d535440`。原表格缺引用的FAIL及快照完整保留，与新PASS分开。

## 保护及任务边界

Root在新实际请求后执行只读核账，`night-batch-preservation-20261018-005757.json`：1283 ID、所有原非空值、41685原业务行、12个夜间尝试快照、163前端指纹保持，quick_check=ok。新增模型/会话/消息/job/附件/快照只允许对应已审收据；11个新增session及认证时间字段例外明确列出。

AI-T08及AI-T09实现单元据此完成。完整UI/在途关闭恢复、性能反馈、本地部署与全库资料交付仍分别执行，不用本子项替代。真实文字PDF与旋转扫描、模糊/加密/损坏等记录见[文件证据](../AI-T09/2026-10-18-real-pdf-table-ocr-worker.md)；实际低于OCR置信阈值的扫描件未验证，只有隔离worker保守阻断通过。
