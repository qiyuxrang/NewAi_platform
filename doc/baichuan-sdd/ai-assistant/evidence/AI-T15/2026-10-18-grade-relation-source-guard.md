# AI-T08 / AI-T09 / AI-T15：等级关系的默认精确及来源门禁

2026-10-18 00:09（北京时间）冻结。本轮完成后端实现与隔离验证；尚未重载服务或执行新的真实模型验收。前端保持冻结，未访问/写入真实企业数据库。

## 真实问题及语义契约

前轮 [六场景真实验收](2026-10-17-night-real-query-files.md) 中，合成DOCX原文“设备制造商必须提供CCRC二级证书”实际被模型提取为 grade_at_least。原验收确实验证了制造商主体与未知结果，却未检查这条默认等级关系，不能据此声明默认精确关系通过。原收据、条件及快照原样保留，不将其改成 grade_exact。后续根代理在AI-D23同步规格与验收语义。

本轮遵守 AI-FR04：明确等级默认精确；grade_at_least 只能来自对应类别、等级、主体的显式“及以上/不低于/至少”等条款。类别等级方向仍由原带来源/版本的规则计算；本门禁不按数字/字符串大小排序，也不重写已有规则。

## 改动及安全边界

仅改 `portal/baichuan_assistant_worker.py`，新增纯模块 `baichuan_relation_guard.py` 和独立 `tests/test_baichuan_relation_guard.py`。

- SYSTEM明确“CCRC二级”默认精确；仅自身类别/主体原文有关系时才提取 grade_at_least，附件谓词逐项给出来源块引用。
- 新模型条件经严格schema/来源所属检查后，逐个审查 must、should及布尔子节点中的 grade_at_least。附件正文仅取本job的同owner、同会话附件实际已解析块；必须命中该谓词自己的 source_refs。顶层引用、别的块或别类“及以上”不能提供许可。
- 门禁只验证有限、可直接定位的关系短语及字面等级；出现多主体/多同类范围、否定、过长/跨段或不确定表达时拒绝推定。无需/无须/不必/不需要/不需/可不/免于等非必需表达同样不能许可关系。
- 不能证实关系时不擅自改成精确：保存原模型条件及等级关系缺口、明确澄清问题，任务 awaiting_input 并释放租约；不匹配、不生成快照、不触发导出。待附件ID保留，同会话补充可重用已解析文本。
- 成功验证关系的身份摘要记入checkpoint；无关追问可继承相同、已通过门禁的关系。未通过的旧关系或待澄清关系没有默认许可。取消另一个文件类别后，同样保留剩余已通过关系的审计标记。
- 当前job已有持久条件直接按原恢复，旧快照不重写。已存在但没有新门禁证明的历史关系仍保留在旧结果；新一轮需要有效证明，不能据“历史已有”自动扩大范围。

这不是完整白话解析器，不替代模型对逻辑/主体/评分项的理解，也不把不支持表达猜成另一种条件。复杂但正确的关系可能进入同会话澄清，属于保守限制。

## 实际隔离检查

复用私有 `model-budget-recovery/run_tests.py`：临时空SQLite迁移至0046，每条数据库连接断言在临时目录，禁DNS、TCP和socket连接；网关全部mock。没有SQL访问真实库、外部网络或真实模型调用。

| 运行 | 实际结果 | 说明 |
| --- | --- | --- |
| 首轮关系模块 | 22 tests，2.283s，OK/0skip | 原语义及恢复边界 |
| 6相关模块 | 94 tests，49.570s，OK/0skip | 关系24、预算恢复14、助手11、集成19、文件19、查询策略7；在随后否定词补充前导入的版本 |
| 新增否定后关系模块 | 26 tests，2.417s，OK/0skip | 含7种非必需表达及缺引用/别类文字 |
| **最终最新3模块** | **60 tests，15.478s，OK/0skip** | 关系27、文件19、预算恢复14；总进程22.915s，包含最后的取消后继承修复 |

新测试实质覆盖：默认精确；无关系原文不许可；自身明确关系及同类别/主体；同句跨类和跨块借词拒绝；仅顶层来源拒绝；否定/非必需词；错误等级与12/十二≠2；多主体歧义；should/NOT节点；已验证追问/无关城市与别类精确条件；旧未校验/待澄清关系不能继承；全局改精确；awaiting_input租约释放与不导出；保留附件、0重复解析、澄清后精确；旧持久条件不重新调用模型；取消其他类别后的关系继承。

实际命令：

```powershell
.runtime/company-test/python/Scripts/python.exe .runtime/baichuan-ai-local/model-budget-recovery/run_tests.py portal.tests.test_baichuan_relation_guard portal.tests.test_baichuan_file_conditions portal.tests.test_baichuan_model_budget_recovery
py -3.14 .runtime/baichuan-ai-local/night-acceptance-20261017/grade-relations-prepare-check.py
```

Python编译检查通过。准备脚本的纯临时测试禁止SQL/HTTP/DNS，验证两个DOCX的真实段落、固定提交ID、重复prepare不覆盖，结果PASS/0SQL/0HTTP/0模型。后端与前端服务未重载。

## 准备好的下一真实单元（未执行）

私有 `.runtime/baichuan-ai-local/night-acceptance-20261017/real-grade-relations.py`，默认仅prepare；新目录 `grade-relations-20261018/`。两份公开合成DOCX均含投标人电子精确二级，制造商CCRC分别为“二级”“二级及以上”。仅product角色，最小必要模型调用2次，不发健康调用/企业名册/内部资料；不新增人工用量硬上限。

每次conversation/upload/message写入前先记提交意图及固定clientID；重复运行复用已有返回ID，不确定提交仅只读找回，不能重发。上传恢复以同owner/同会话/原文件名/SHA精确定位。真实结果要求默认CCRC=grade_exact、显式关系=grade_at_least，制造商主体、具体来源块、已解析附件、无unresolved、固定候选及0查询研究；前后保护企业/原资质/人员/旧会话快照。失败保留状态与已有ID，不自动重发模型。

**根代理完成后端重载并明确通知后**才执行：

```powershell
py -3.14 .runtime/baichuan-ai-local/night-acceptance-20261017/real-grade-relations.py --execute
```

本轮尚未执行上述真实命令；prepared receipt仍为 `prepared_not_executed / model_calls_executed=0`。

## 文件、日志与恢复点

私有夜间目录：`relation-guard-tests-001.log`、`relation-guard-combined-001.log`、`relation-guard-tests-002.log`、`relation-guard-final-001.log` 保留每轮实测结果；`grade-relations-prepare-check.py`、`real-grade-relations.py`及两个DOCX/receipt提供下一单元。

冻结SHA256：

- worker：`81c24c62f50169ed379d234b4ff15939c1ced25bc567d39ff6de0c4ecf58d3fb`
- relation guard：`26a8ab9e7b921dc474f6eb5c1bbaa739a07e1181fcea1a8864a78fbb3f77c737`
- 专项测试：`e9da5fcc73b93ec0a3860aa467e1172b860850f716d17551f63a9dbb1e567da4`
- 新真实脚本：`62289e0dd3a9baec9fcd70aee69f756a6992cab5239e302ceb8f7ec2e7d13f1f`
- prepared receipt：`9cd870e33444a145575f2f56aad89507f3c18a3a695101024b40176f0416c195`

共享tasks/progress/checkpoint未编辑，交根代理统一同步。当前恢复点为“后端审阅/加载后，执行两份新文件的真实等级关系验收”；不能把本轮隔离通过当作该真实单元通过。
