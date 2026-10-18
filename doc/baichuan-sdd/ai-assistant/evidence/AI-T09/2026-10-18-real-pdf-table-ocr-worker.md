# AI-T09 / AI-T15：文字PDF、表格DOCX和扫描PDF实际接入

执行时间：2026-10-18 00:28:09–00:28:34（北京时间）。本轮三个真实场景为 **2 PASS、1 FAIL**，不能标记全通过。既有两角色与等级文件验收不重复请求。前端、企业资料、原资质和人员资料均未修改；实际只新增所属会话、附件、任务及结果快照。

## 固定输入与真实结果

| 场景 | 输入与断言 | 实际结果 |
| --- | --- | --- |
| 双页文字PDF | 第1页投标人电子与智能化精确二级硬要求、ITSS二级评分；第2页制造商CCRC精确二级、负责人个人CISP。逐项硬谓词必须引用准确页。 | PASS：native completed，2页定位正确，主体及硬/软分离；个人CISP明确保留在unresolved，没有错归投标人。 |
| 资格表格DOCX | 第1表第2行电子与智能化硬要求，第3行ITSS评分，第4行制造商CCRC硬要求，第5行个人CISP。 | FAIL：解析completed，行2–5定位真实存在，主体/等级/人员缺口正确；但硬谓词没有自己的source_refs。全文件引用不能代替逐项表格行。 |
| 旋转90度扫描PDF | 真实栅格，无原生文字层；投标人ITSS二级，制造商ISO9001仅优先。 | PASS：OCR needs_review，3个第1页bbox来源；ITSS精确二级，ISO9001留优先/未覆盖说明，人工核对警告保留。 |

各快照1283家：confirmed 0、candidate 1283、excluded 0；research_status=not_requested。真实模型日志16/17/18，均success，共3次，无自动重试；输入tokens 3738、输出1420，累计网关耗时15256ms。每个任务的持久model_calls计数为1、研究sources为0。

扫描件本身识别置信度0.9833–0.9994，本轮不能声称已实际得到低于0.85的物理扫描识别。低置信度进入worker后的阻断另以隔离测试验证。

## 原始失败与保护

私有原始收据：`.runtime/baichuan-ai-local/night-acceptance-20261017/pdf-table-e2e-20261018/receipt-original-001-missing-predicate-ref.json`，SHA256 `ac630ef290a87f635d80931a3fd2dd03166200353004d25e52a3fb9f7a63eac6`。保留原失败，不更新为成功。

表格失败快照`94b80263-57b3-4db5-8d3e-5e496f938656`，job `b4a9f922-2506-4f58-84ed-da881ed300e9`。持久条件的顶层来源含附件b1–b7，electronic/CCRC硬谓词及ITSS优先谓词均无逐项source_refs。worker会把顶层来源替换为授权集合，因此不能凭该顶层集合断言模型原始JSON具体输出了哪些根引用。模型原始content未持久保存，ModelCallLog仅保存调用状态/用量；可证明的是编译条件缺少逐项来源，编译器不会删除合法逐项source_refs。

执行前后逐行摘要保护企业、原资质、人员；全部旧会话/消息/快照摘要和研究计数均一致。额外仅SQLite `mode=ro`核账三个新快照内容未变，3任务调用计数一致，见同目录`post-readonly-audit.json`；该核账0HTTP、0模型、0数据库写。正文/附件仅合成公开条款，未发送企业名册、电话或内部文件。

输入文件SHA256：文字PDF `2f562a4a30c01438445fb36e6cf79d2cf2e4e63e24de6ddf25b711ab41e6f53f`；表格DOCX `8e695f00504404e0a1953db37213cf4219227fc3b08a31ea7dd8e75f3cc3b1e2`；扫描PDF `bcb49a2a37db84ee03a65f8edb01c982f40c94b85d70defa54fb8ebd782fb183`。PDF已渲染逐页检查，表格为真实Word表。

## 修复与隔离验证

本轮最小后端修复：

- SYSTEM提供逐项表格引用完整示例，明确顶层引用不能替代硬谓词自身来源；模型上下文增加真实block的source_ref、text及location映射。
- 混合输入的当前owner文字提供`message:<真实消息ID>`定位；文字条件可引用消息，文件条件引用附件，不要求用户拆开发送。未知/他人消息和附件引用继续拒绝。
- 新文件硬谓词缺少逐项来源时，保留实际条件/缺口/待处理附件，进入awaiting_input并释放租约，不匹配、不研究、不导出，不猜配来源。追问沿用相同owner/会话附件；已持久条件恢复不再调用模型。
- 根审阅提出的旧unknown文件guard反例已实际复现：模型在纯文字追问中漏掉旧文件条件时，原校验先执行、再合并旧guard，导致completed。失败日志`source-guard-legacy-counterexample-001.log`保留。修复将合并放在校验前；无新文件时仅检查旧文件guard叶，不强迫新增纯文字条件伪用文件来源。缺口只从真实UUID且同owner/会话的附件恢复pending。已有旧checkpoint重试也检查归属缺口，不重放模型；不重写旧快照。
- 旧文本条件与已有效前轮文件条件可继承；文件取消guard仍只识别附件来源，不能把消息引用当作文件条件。旧快照不重写。

来源完整性gate只证明“有可访问定位”，不替代AI对条款语义的解释，也不证明被引用块必然支持该谓词；等级关系另受D23对应主体/类别来源guard约束。

实际命令：

```powershell
py -3.14 .runtime/baichuan-ai-local/night-acceptance-20261017/real-pdf-table.py --execute
.runtime/company-test/python/Scripts/python.exe .runtime/baichuan-ai-local/model-budget-recovery/run_tests.py portal.tests.test_baichuan_source_guard portal.tests.test_baichuan_ocr_worker portal.tests.test_baichuan_relation_guard portal.tests.test_baichuan_file_conditions portal.tests.test_baichuan_model_budget_recovery portal.tests.test_baichuan_assistant portal.tests.test_baichuan_integration_review
```

初轮7模块106项PASS，49.746s（隔离启动/迁移合计57.704s），0skip。随后补真实foreign-owner消息引用，来源模块13项再次PASS，2.213s（合计9.818s）。根审阅后补3条旧文件恢复专项，最终7模块 **109项PASS / 50.334s（总57.951s）/ 0skip**，日志`source-guard-isolated-007.log`，来源模块现16项。隔离测试强制临时SQLite与禁止网络，模型mock，0真实库访问/网络/模型调用。初次测试命令误写模块名、旧测试fixture缺块正文或新逐项引用导致的失败日志均保留；原integration中“有效文件保留提示”控制fixture补逐项来源，真实旧unknown树另有反例测试，未把未知来源改成已知。最终命令通过。

最终冻结SHA256：worker `b2af9eb5a839599495a223a95d454a6438e9cc3fa8ee57aa665bf96b4906df39`；source guard `540ce3a430f66868390d5b28bd8c591e80652edbf6db5646ca596e7a967802a5`。静态编译、diff-check通过。

新增OCR worker隔离测试3项：已核实地区事实原本可confirmed；低置信度needs_review将总体判定降为unknown/candidate；缓存needs_review即使未再次返回原警告也不会提升确认。该范围是受控低置信度worker回归，不冒充真实低质量扫描的模型实测。

初次冻结时来源缺口修复尚未加载/真实复验。新固定ID单表格复验`.runtime/baichuan-ai-local/night-acceptance-20261017/real-table-sources.py`，默认0SQL/HTTP/模型；只复验原失败表格，最多1次新模型任务，无自动重试，PDF与扫描的已有通过不重跑。新验收允许合法当前消息在顶层出现，但仍要求每个文件硬谓词准确引用附件表格行，不放宽原失败断言。

## 修复加载后唯一表格真实复验

根完成所有`test_baichuan*.py` **321项PASS / 170.276s / 0skip**，并于2026-10-18T00:55:50.313463+08:00仅重载所属后端，确认prepared=loaded后，本代理获得新执行窗口。以下实际只发生一次新提交，未重复原PDF/扫描，也未重试原失败job。

```powershell
py -3.14 .runtime/baichuan-ai-local/night-acceptance-20261017/real-table-sources.py --execute
py -3.14 .runtime/baichuan-ai-local/night-acceptance-20261017/table-source-post-readonly.py
```

2026-10-18 00:56:36–00:56:44真实 **PASS**：

- 投标人electronic grade_exact=2的自身来源是b4，对应第1表第2行；制造商CCRC grade_exact=2为b6，第4行；投标人ITSS仅should，来源b5，第3行。
- 个人CISP硬性条款明确进入unresolved，未当成投标企业证书、未删掉未知硬要求。实际结果confirmed 0/candidate 1283/excluded 0，research_status=not_requested。
- 新会话`2b83ee5b-7cd4-431c-9b82-cd529dce7bfd`，job `61b6e255-95d7-45fa-ad9d-5def600c3cac`，附件`419e41df-b128-4000-9c93-e011194194a8`，快照`7580e464-1601-43f8-abab-70b8691904c2`。
- 实际ModelCallLog 19，success，1次；网关4779ms，输入2271/输出465tokens。无自动重试、无研究源或资料写入。
- 后审`mode=ro`额外读取1283条结果，四字段`condition_tree/results/counts/fact_cutoff_at`按`json.dumps(SQL-row, sort_keys=True, ensure_ascii=False, default=str).encode()`得SHA256 `a26887e89cdad8deaea2b7e3302c2d9c1d147067b11e7ec32e6983eb7e2269dc`，与执行器第一次记录一致。新增ID清单为1会话/2消息/1job/1附件/1快照，无新导出。
- 执行窗口企业、原资质、人员、全部旧会话/消息/快照及研究计数摘要一致，163个冻结前端文件hash一致。后审本身0HTTP/模型/数据库写。

私有新证据目录`.runtime/baichuan-ai-local/night-acceptance-20261017/table-source-retest-20261018/`：`receipt.json` SHA256 `b3b640f8e582da70e538a219e51b3ac4b7784e1490289f15eefb586a15bfcd1e`；`post-readonly-receipt.json` SHA256 `873cd13ee1ad0f1e17c0203ad64c2081b5274c768e4eaaae8613cdba3d535440`。原表格失败快照和失败收据保持原样；此节是独立修复后成功记录，不能倒改原验收结果。物理低置信度扫描仍未新增实测，前述模拟worker测试范围不扩大。
