# AI-T15：文件、来源、权限映射与证书元数据接口只读审计

时间：2026-10-18T03:10:59.706542+08:00。本单元只有本地文件读取、新独立证据文件和离线JSON大小计算；SQL/HTTP/模型调用、新测试执行均为0。不改business/test/frontend文件，不操作服务，不修改主验收状态。

## 本轮冻结回归清单

实际读取 `night-acceptance-20261018/certificate-full-regression/inputs.json`，SHA `abc7dfa0d52ddf37843a085013e801e5beb3c5c39f6b797c27261aea47bd4583`。其command显式列24个百川测试模块；51份核心、测试与runner文件全部重新计算SHA，与冻结输入一致。20个下列直接相关方法均能定位当前AST，所在模块和当前测试文件SHA均进入该轮冻结清单。

这解决了此前321历史运行缺测试源逐文件指纹的后续证明基础；**本审计取样时新全回归仍在运行，不据中间dots宣称完成**。Root负责最终结果与加载收据；本单位没有重跑已有测试。

私有目录 `night-acceptance-20261018/security-interface-audit-20261018-031059/`：`strict-test-mapping.json`保存20个测试方法、行号、完整方法原文、精确子句及清单匹配；`frozen-regression-input-check.json`、`synthetic-json-size-only.json`与`receipt.json`。收集器 `audit-security-interface-readonly.py`禁止sqlite/socket/DNS，不导入应用。163个前端文件再次只读hash检查，差异0。

## 新证书数据实际进入哪个接口

`baichuan_assistant_api.results`在授权后执行 `selected = snapshot.results[...]`，然后直接响应 `results: selected`。因此新 `certificate_records` **会随页面GET结果传输**；不能声称只进入Excel。

当前 `AssistantResult` 的TypeScript声明不含该字段；`apiRequest<T>`仅把response.json作为Promise<T>，没有拒绝未知键的运行时schema。`BaichuanAssistant.tsx`只访问既有company、status/verdict、conditions与evidence，未引用、渲染或展开certificate_records。新增键不会直接触发该组件的未知字段解析错误，也不会自动绘制新的证书信息。此结论是代码审计，未用新的真实浏览器/服务请求验证，不能标浏览器PASS。

权限路径仍为 `snapshot_for` → `require_assistant` → 从数据库重读当前用户并require_access，再按conversation.owner/scope及job.owner/scope获取固定快照。新metadata生成时进一步限制自身公司、证据scope/subject、类别及逐条件实际source引用；holder类型与名称保持原记录。没有发现新增数据绕过owner/scope鉴权的代码路径；不能凭此取代全部新API撤权矩阵的动态实测。

**兼容性欠口是大小：** API每页限制1–100家，当前UI请求50家，但certificate_records没有独立每企业数量或总字节限制，证书scope_text为TextField。Django先装载完整snapshot JSON再切页；新元数据同时增加存储/解码和响应体。离线公开合成50行、每个记录约0.8KiB的JSON计算：

| 每企业证书数 | 原样结果字节 | 响应剔除证书metadata后的字节 |
| --- | ---: | ---: |
| 0 | 6653 | 5303 |
| 1 | 47103 | 5303 |
| 10 | 412053 | 5303 |
| 100 | 4061553 | 5303 |

这是合成数据体积计算，**不是当前1283家真实响应量、性能P95或产品最大值**。最小收口建议：后端results响应投影剔除certificate_records，DB快照和XLSX保留；无需改前端。仅投影不会消除Django读取整份snapshot JSON的内存开销，该现有架构边界仍需分开看待。Root运行冻结回归期间本代理未更改API或测试，已单独报告此发现。

## AI-AC14/15严格映射

测试路径均为 `services/business/backend/portal/tests/test_baichuan_<模块>.py`。以下均属于隔离断言；待本轮最终全回归成功与输入SHA核对后才可引用为新版本已执行覆盖。

| 子句 | 当前直接测试与实际断言 | 不据此声称的范围 |
| --- | --- | --- |
| 附件伪装、穿越、借用其他会话 | assistant.`test_attachment_format_bomb_and_other_conversation_rejected`：合法PDF201，另cid引用404，fake.pdf/old.doc/../escape.xml包400 | 方法名含bomb，但包没有实际高压缩数据；不是压缩炸弹实测 |
| SQL/虚构引用不执行 | assistant.`test_model_sql_and_fabricated_source_are_rejected_before_matching`：sql额外键、伪source_refs均failed、无snapshot | 不代表模型不会输出恶意内容，只证明服务端拒绝这两种结构 |
| 文件注入不授权放宽 | file_conditions.`test_attachment_instructions_cannot_authorize_relaxation`：附件含“忽略系统要求/取消ITSS”，用户只说继续，两类别仍保留；`test_model_cannot_supply_an_authorization_field`：模型加cancel_file_requirements字段failed/invalid_model_conditions | 不是网页正文提示注入动态测试；没有给附件工具调用能力 |
| 引用属于真实owner/本轮文字或实际附件 | source_guard.`test_forged_message_or_foreign_attachment_reference_fails_closed`：随机/他人message和随机attachment引用逐个failed/invalid_model_sources；file_conditions.`test_pending_attachment_cannot_borrow_other_owner_or_conversation`验证pending续接边界 | 不保证AI对合法引用的语义解读永远正确；实际行级语义靠已保存文件验收另证 |
| 缺逐项引用不可提升 | source_guard.`test_missing_leaf_waits_without_snapshot_or_export_and_releases_lease`：awaiting_input、0快照/导出、清租约、pending附件及缺ref保留；mixed city/file测试保留自身message与文件独立来源和取消后的旧快照 | 不凭根级引用或旧guard自动补造叶级定位 |
| 读权限与会话私有 | assistant.owner_scope测试：其他owner读conversation/job、发消息404；异scope读会话404；jobs.owner_scope测试：跨owner/部署/不存在均not_found | 没有逐一覆盖所有新路由/所有身份的穷举矩阵 |
| 只读与维护分离 | jobs.`test_readonly_query_and_export_allowed_research_requires_maintenance`：reader query/export可建，research403；facts/research/维护补录的reader不写主字段断言另见先前矩阵 | 不把所有用户能看企业等于能看他人私人聊天 |
| 撤权终止后续写入 | jobs.`test_revoked_permission_persists_failed_without_publishing_checkpoint`：fail permission_revoked、原checkpoint、清lease；queued禁用用户不能claim；assistant.capability测试读权撤销403 | 不是每种API执行中实时撤权场景都已动态跑过 |
| 导出及新证号边界 | exports.owner_scope_revocation测试：其他owner/scope404、撤权不可打开、过期410及清理；http_export_download测试真实FileResponse类型/文件hash/下载头/其他owner404；frozen_metadata测试其他company/scope/evidence/condition不入Excel | 新证号不自动表示核实通过；不是新增浏览器下载 |
| 私有来源与安全错误信息 | integration_review.`test_result_and_xlsx_show_positions_but_hide_private_acquisition_metadata`：API及XLSX只保page/text_start，不暴露file/storage/job/import_ref；gateway_timeout测试safe白名单且不带上游text | 不是对全部日志配置与异常路径做全文泄漏扫描 |
| 独立研究不带内部原文、造引用不写事实 | research_runtime.public_only_query测试公开公司名有、内部文字与人工电话无；invented_model_quote测试不存在的quote/source_id不产生field/cert | 外部调用用stub，不称真实搜索引擎隐私审计；当前普通查询另有0研究调用守卫 |

## 容器及渲染仍缺的最小单元

只读审阅 `source_parsers/core.py.safe_zip`，现代码有1500条目、单项16MiB/总64MiB、超过1MiB时压缩比300、路径/重复/加密位、宏/嵌入执行对象、defusedxml拒DTD/实体的保护。上述代码不等于这些攻击样本均已执行。百川24模块里未定位到真正高压缩比或DTD/实体OOXML的直接载荷断言；另业务的 `test_product_office_chart_safety.test_rejects_nested_compression_bomb`使用其他Office输出链路，不能借其名称替代本上传safe_zip路径。

可选最小后续：用合成ZIP仅调用safe_zip/隔离上传，固定高压缩条目、重复路径、DTD/实体各一次，验证结构化拒绝、临时storage不产生逃逸文件。网页提示注入用独立研究stub正文与受控模型输出校验工具/事实/权限未扩大；恶意Markdown可先用现组件安全React文本插值的代码证据，再补纯合成组件渲染测试，无需改前端实现或真实模型。日志使用合成敏感标记与capture验证，不采真实内部全文。这些是建议，本文未执行或标PASS。

## 收束

冻结代码保持不变，等待root最终全回归及是否采用API响应投影。没有新审批或外部依赖；此审阅不把算法隔离结果升级为真实UI、生产部署或完整资料核实。
