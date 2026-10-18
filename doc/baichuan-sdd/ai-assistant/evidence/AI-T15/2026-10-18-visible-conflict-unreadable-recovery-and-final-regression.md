# AI-T15/17：可见澄清、不可读附件恢复与最终463回归

记录时间：2026-10-18T09:03:39.492415+08:00。工作区HEAD仍为ef1676cd8327d693dab897c45a234ba91413884e，未提交/推送。按AI-D29继续SDD，AI-D27独立资料补全跳过、AI-D28旧资质可信、163前端冻结均保持。

本单元已在所属本地加载并通过原页面验证。原SDD完整验收尚未全部通过：5秒首结果目标未达、原生无背景模糊浏览器在页面创建前阻塞；全库研究延期、远程环境未操作。

## 问题与修复

此前真实混合输入实际FAIL：文字要求一级、同一附件要求二级，内部条件树虽保留冲突和附件硬条件，回复只显示数量。worker现把有界待澄清事项写入持久助手回复，原页面即可显示；不改原条件树、匹配等级或前端。

此前真实扫描OCR关闭实际FAIL：parser返回failed和空块，worker仍预留并到达模型stub。现对failed/空白/无可读块在模型前停止，保存原附件、原页级结构化警告与attachment_issue，错误码attachment_unreadable，模型/预算/快照均0。真实partial有正文仍可理解，但警告继续阻断确认；严格兼容旧缓存仅有独立正文和无text键locator的形式，不捏造逐段正文。显式空text及混合缺失/空白块不借兼容分支放行。

原页面未提供移除待确认附件的入口，因此补后端明确弃用协议。仅真实用户本轮文字精确以“放弃本轮未读附件，改用本轮文字：”或“放弃本轮未读附件，改用本轮文件：”开头时，才可弃用上一失败轮对应的一个未读附件；原件仍保留。完整文字或实际新文件必需，同owner/同会话先校验全部ID。否定、引用、附件内指令、错误失败类型、旧revision/外人ID不生效；无新公开API字段。

恢复保留原已知文件硬条件和紧邻成功快照，并原样继承已校验等级关系与待澄清关系状态。已校验“及以上”不重复询问；原未校验关系继续等待，不提升未知为满足。原请求UUID/内容/幂等、历史快照不改。

涉及生产文件为portal/baichuan_assistant_worker.py及baichuan_assistant_service.py；新增三个独立测试模块test_baichuan_unresolved_reply、test_baichuan_unreadable_attachment、test_baichuan_unreadable_recovery。实际源码SHA已由最终67输入收据固定。

## 实际检查及版本区分

最终完整回归08:54:56—08:59:12，37模块、463项实际PASS，248.323秒，0跳过，67输入SHA前后及加载前均一致。命令完整保存在receipt.json：使用本地Python3.13、scripts/baichuan/check_backend.py和37个portal模块，临时独立SQLite；无主库/真实模型/前端执行。覆盖原433、回复/不可读/兼容/明确弃用与等级关系多轮正负边界，含原两个实际OS硬终止恢复用例。

原失败不覆盖：第一次443项/234.868秒为3FAIL+1ERROR（旧缓存兼容被门禁误拒）；长回复初始测试夹具超条件上限、恢复测试比较Django实例缓存的夹具失败另存；修夹具不削减业务断言。第二轮445项/235.461秒、第三轮461项/247.433秒均实际PASS，但分别早于后续恢复/关系继承修改，不能冒充最终源。最后等级关系三模块64项PASS/23.300秒属于最终完整回归前的针对检查，不与463相加。

真实同一扫描关闭OCR的修复后隔离worker检查在08:31执行：真实parser一次、模型stub0/预算0/快照0、原字节及页警告保留。它是早期门禁修复版本；后续最终源用冻结parser输出及严格缓存/恢复测试覆盖，不声称重跑物理扫描。最终版本另外有下述原页面真实空白PDF解析，二者范围分开。

## 所属本地加载与原页面实际结果

08:59:37完成加载，只替换所属portal/worker，加载前在线备份before.sqlite3及quick_check=ok。原前端PID21632、两网关PID23540/16912及163文件SHA保持。全表行摘要、旧会话/快照/导出、角色/账号和原数据保持；0迁移/重导/seed/模型/研究/构建。四健康HTTP200。当前portalPID1472、workerPID25144。

| 原页面实测 | 实际结果 |
| --- | --- |
| 总经理同一输入文字一级＋合成DOCX精确二级 | PASS；持久回复明确展示一级/二级冲突及需澄清；0确认/1283候选，附件二级硬条件和引用保留。刷新恢复相同cid及sid |
| 原页面真实上传一页空白PDF | PASS；failed/attachment_unreadable，原页级原因及可行替代在助手消息可见；0模型/预算/快照，不猜测内容 |
| 同一会话明确改用完整文字 | PASS；精确二级346确认/937候选，确认ID全集等于当前旧库筛选，新增唯一Model38；原PDF仍保留 |
| 原生reload恢复 | PASS；从原存储恢复同一cid/snapshot，无人工注入cid；相同固定企业列表 |

混合输入cid fafc0f8f-250f-40dc-b41d-9f8c6b97fa59，job ede565a2-8708-4242-be12-1f0366794446，snapshot d5b450a9-1cac-4c32-bcdb-f0953bf59db1，唯一Model37。不可读恢复cid bbf3af65-1867-43b3-9754-c60a16035576，首job b33f505e-cef4-47ac-87c1-8f79bff54c69，替代job 14aba0ea-6a53-43f7-9e5d-c8f80c8ec060，snapshot 3dc1c023-6644-4d23-b669-2fac876ab7c9，附件9906845e-de9a-417e-a610-ba272815beb6。均为原UI唯一native UUID提交、无自动重试，独立headless Edge155.0.4283.45；登录经现有API，不冒称原登录表单测试。

恢复单元精确新增1会话/4消息/2任务/1附件/1快照/1模型，旧36快照及业务数据保持，session34→34、全部旧session行及用户除last_login外字段保持；认证字段独立核账。不上传真实业务招标文件，使用明确合成样本。没有浏览器DOM/CSS/前端修改。

## 最新只读保护、用量与剩余项

09:01:20实际只读收尾：463输入67一致、163前端一致、5所属进程及4HTTP200、quick_check=ok，无queued/running；1283企业/1460旧资质/1622证书。40会话/95消息/62任务/37快照/21附件/13导出/38模型日志，企业/资质/证据/历史会话与研究摘要保持。原Excel和试运行库SHA均保持。

本次AI-D29恢复阶段实际模型日志34—38共5次成功，prompt6149/completion1418 tokens；34/35为计时、36为原冲突失败、37为修复后冲突、38为明确替代。新两轮原页面修复验收仅37/38两次，0重试/健康探测模型调用。未知费用不推算。资料研究/维护写入/新增核实均0；历史95批/295家/641补空与162未核实观察保留，1460旧资质按用户确认可信，不重新核验或改核实状态。

两角色首可见8.2276/5.142秒是有效未达5秒目标的原记录。唯一模型分别4.883/2.503秒；两样本差3.0856秒中模型差2.380秒。POST返回至服务端终态扣模型还剩2.009/1.293秒，缺claim/匹配分段不能进一步强行归因；其他约1.34秒含提交/传输/原轮询/渲染，不能全部归为轮询。后端idle默认1秒、前端1500ms轮询属当前约束；改现有worker poll配置只能有限减等待并增加空闲查询，没有实施或声称能保证5秒。不删除性能目标，不为凑目标减少模型校验或宣称两次为总体P95。千/五千匹配容量已达其独立目标，见[阶段性能与格式矩阵](2026-10-18-resumed-remaining-ui-and-performance.md)。

原生不支持backdrop-filter的Firefox运行库仍在page前WinError14001，未绕过系统限制、未再安装或重试。AI-AC01该分支BLOCKED，不冒称产品失败或通过。原无效反馈计时null保留；合成race的11.3/13.6ms是另外有边界的DOM反馈。前端冻结、资料延期、远程未部署保持，原SDD整体验收不能批量DONE。

## 原始证据与恢复点

下表均相对于.runtime/baichuan-ai-local/night-acceptance-20261018，原件不进公共源码，SHA为实际读取值。

| 原件 | SHA256 |
| --- | --- |
| `remaining-defects-final-regression-attempt4/receipt.json` | `83849721138b1fb7e387bc1ad6c5fc901e41711d6c8ce3bc0c757cc6bc15e171` |
| `remaining-defects-final-regression-attempt4/tests.log` | `64bfc06a026b0402291edc1faefe58f5519fa9678c17dacdf5083a3f318c6d9d` |
| `remaining-defects-owned-load/intent.json` | `10af9488aca933cfcf8192ebf1d896cb2e4b5f597059743123ad0ef22ac0f29a` |
| `remaining-defects-owned-load/receipt.json` | `fbf0d782e0068807da156dacc200be11d8c7100b5d7b74a397e6111e28219e6a` |
| `text-file-conflict-native-fixed/receipt.json` | `1d22b7a59d49c6cb006be82c313e708f6b7519467136855bf7021f9a712ad772` |
| `native-unreadable-replacement-20261018/final-receipt.json` | `ffd2a4aba180f64d901ba60e5656f0f707e00cfcf9fdb52f5afff79668725e2d` |
| `native-unreadable-replacement-20261018/post-readonly-audit.json` | `8cf7a3cbaf32d3f2492f02e811fcf6ba47247909fcbf0e3fd09d63506e781307` |
| `remaining-repair-final-readiness/receipt.json` | `d8079c5a9ae94ce058276d73574039d6122d1e3bfaef41a8776122fe7a86d36a` |
| `ocr-disabled-real-worker-fixed-20261018-0833/receipt.json` | `51c0bb838a8482c89811d23ff920344e74f2590e7d9b4651c2cca29d2f5ad7d2` |
| `grade-guard-recovery-evidence-20261018-0855/receipt.json` | `df1f0514c0e637c1fa345b5146cc6f708c9d39ce149d61a9f02dba2e8bc50f53` |

原失败与阶段数据见[此前独立阶段证据](2026-10-18-resumed-remaining-ui-and-performance.md)，不修改其历史字节。后续从checkpoint恢复剩余适用AI-T16/17验收，不能重跑本次原UI或资料研究；性能目标未达与原生浏览器依赖分别处理。自动化仍实际PAUSED，本轮为用户直接继续执行，不声称后台定时任务已恢复。
