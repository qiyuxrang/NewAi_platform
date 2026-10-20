# AI-T15：验收逐句证据候选核账（只读）

取样时间：2026-10-18T02:59:37.440945+08:00。本文供 root 审阅，不修改主验收状态，不是新的功能执行或最终交付。没有 SQL、HTTP、模型调用、服务操作、前端或业务代码改动；没有重跑测试。

## 证据版本与证明限度

本次实际重新计算 `final-restart-receipt.json` 所列28个后端文件 SHA：全部与 prepared、loaded 一致，差异0。当前24个 `test_baichuan*.py` 模块通过 AST 实际枚举321个测试方法；逐方法位置、当前文件SHA及 assert 原文已独立保存。

最终历史日志 `combined-backend-source-guard-r2.log` SHA为 `c2c8c18c9bb485e25a4a784bf4d28c4d6043a3676453397678f8582f75c89366`，实际含 `Ran 321 tests in 170.276s`、`OK`，原FAIL保留。[当时合并记录](2026-10-18-source-guard-merged-acceptance.md)说明隔离新文件 SQLite、全部百川模块及零跳过。Root确认当时按全部模块传给 `scripts/baichuan/check_backend.py`；该脚本自身默认只跑 assistant，不能把当前默认命令误写成当时全套命令。

**没有当时测试源逐文件冻结SHA，也没有逐测试 verbose 日志。** 当前321方法与历史321总数相同，是可审阅的范围对应，不能声称每个当前断言已有独立历史执行收据。下文“建议整项提审”依赖 root 接受上述历史记录与当前代码一致性的证明限度；需要更强证明时，只重跑所选条款对应模块并冻结测试SHA，不必再跑未相关全套。

私有新目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/ac-evidence-audit-20261018-025937/`。包含 `intent.json`、`receipt.json`、`core-hashes.json`、`current-test-assertions.json`、`input-hashes.json`；收集器 `night-acceptance-20261018/collect-ac-evidence-readonly.py` 对 sqlite/socket/DNS设拒绝守卫，不导入应用。

## 20项总览建议

以下是建议，不是 PASS 状态。算法隔离条款不强加真实证书或 UI 前置；实际角色/部署/数据交付条款不以算法测试代替。

| 条款 | 候选结论 | 剩余最小范围或证明边界 |
| --- | --- | --- |
| AI-AC01 | 部分实际通过 | 两角色三宽度、收起/覆盖/键盘/减少动画已有证据；真正不支持背景模糊的运行环境仍 NOT_RUN，不能将浏览器支持但关效果等同于不支持。 |
| AI-AC02 | 实际流程加隔离竞态已有覆盖，建议分句提审 | 真实两角色文字/追问、原UI输入法、固定请求与迟轮隔离分别有证据；没有同一真实UI双模型并发回包的独立收据，不把隔离竞态写成真实并发。 |
| AI-AC03 | 实际文件核心已覆盖，建议分句提审 | 产品与GM文字PDF、表格/段落DOCX、附件加文字、硬软/主体/个人未知及引用均有实际产物；文字与文件冲突/放宽主要由隔离测试证明，旧表格FAIL及其原context刷新NOT_RUN保留。 |
| AI-AC04 | 保留物理低置信度缺口 | 旋转、无法识别的模糊、加密/损坏和缺OCR有证据；固定blur4关键ITSS为0.996，没有低于0.85的真实关键扫描输出。隔离0.61 stub阻断不是物理低置信度。 |
| AI-AC05 | **建议整项提审（隔离算法口径）** | 精确、同类OR/跨类AND、相反等级字典、NOT未知、冲突及SQL/字段边界有实质断言；实际等级提取另有D23文件收据。受历史测试源指纹限度约束。 |
| AI-AC06 | **建议整项提审（隔离主体/范围口径）** | 父/厂商/个人/产品/联合体、范围不符均候选；明确硬失败被排除且保留条件依据。不是1460条真实证书核验。 |
| AI-AC07 | **建议整项提审（隔离日期口径）** | 日期包含边界、过期/未生效/缺日期/撤销、历史/未来日期与撤销时点匹配均有正反例。未查撤销仍未知。 |
| AI-AC08 | 分类/保留/放宽已覆盖，零确认解释建议单独确认 | 四态分类、无损预筛、优先项不抵消、显式放宽/版本/保留旧快照有测试；真实0确认1283候选有产物。零确认时“范围与缺口”的完整用户可见解释尚未找到独立逐句断言。 |
| AI-AC09 | 查询零研究可提审；独立故障矩阵仍部分 | 旧开关全开下文字、文件、追问、重试0研究/搜索/正文有守卫；独立失败/缓存/正文/冲突保护分散有证据，真实慢网与冲突来源组合的逐项计时/快照不变不宜统称已验。 |
| AI-AC10 | **建议整项提审（实现与所属本地增量维护口径）** | 同值/冲突/错主体/CAS/删除旧子项留历史/回撤拒绝后续人工均有实质隔离断言；51批取样只读核账与后续维护是独立实际证据。 |
| AI-AC11 | 固定清单/断点已覆盖，合并场景仍需明确 | 隔离固定IDs/版本/增量/重试保留分母及实际1283清单存在；未找到企业“合并”全过程及原Excel不可读而保留来源的直接端到端断言。 |
| AI-AC12 | XLSX核心可提审；证号前导零缺口保留 | 实际三表/默认确认/显式候选/前N/空结果/字段/电话信用代码文本/旧文件不变/下载已有证据；当前输出字段不含证号，也无证号Excel读回断言，不能全句放行。 |
| AI-AC13 | 持久任务与真实关闭恢复已覆盖，断网范围单列 | OS进程竞争、fence/租约/取消/重试/澄清/预算及真实queued关闭刷新有证据；真实浏览器断网恢复未见独立收据。旧GM表格原context未测仍保留。 |
| AI-AC14 | 权限主要边界覆盖，逐入口矩阵待补齐 | reader/维护/无权、跨owner/scope、撤权租约写、下载撤权均有断言和真实角色隔离；当前未找到每个新入口针对账号撤销/不存在统一响应的穷举实测矩阵。 |
| AI-AC15 | 多层安全边界覆盖，不能整项统称PASS | SQL/schema、附件伪装/穿越、私网/重定向、公式、私有来源/错误正文有断言；真正高压缩炸弹、网页提示注入、恶意Markdown渲染及日志全文不泄露的独立断言不齐。 |
| AI-AC16 | 隔离与本地演练范围已覆盖，整项需root合并审阅 | 迁移往返/旧CRUD/CAS、真实backup副本flag-off、所属worker暂停原列表可用及恢复都有产物；不是远程生产回退，不宣称未迁移库能运行全部新代码。 |
| AI-AC17 | 已有千/五千与资源证据，保持统计边界 | 分段/缓存/P95、预算/竞争、真实UI反馈与PDF/扫描计时有证据；有限样本不保证总体P95/全局RSS/多进程总槽。用户“无额外模型预算”不被改为新产品硬上限。 |
| AI-AC18 | 所属本地两角色矩阵核心已通过，部署范围受限 | 实际文字/DOCX/PDF/扫描/已有导出/原页面恢复与版本保护已有证据；独立研究权限CLI与普通UI分开，远程生产未部署，旧失败不覆盖。 |
| AI-AC19 | 阶段数据审计通过，完整交付未完成 | 51批样本逐源/字段/旧行/幂等标记核账；此后批数增长不改该取样。1460资质独立核验0、原网页一份缺失、全部字段仍缺，不能整项最终放行。 |
| AI-AC20 | 恢复材料可用，最终交付仍需root审核 | 原失败/未验/采用来源及许可证和版本分开保存；目前全20主行NOT_RUN与已有证据不协调，由root审阅建议后更新，不由本审阅直接改。 |

## AI-AC05：逐句对应

测试文件位于 `services/business/backend/portal/tests/`，以下名称可在私有 `current-test-assertions.json` 查询完整行号与 assert。

| 输入/必须结果 | 测试及实际断言 | 类型 |
| --- | --- | --- |
| 精确二级不扩大 | conditions.`test_exact_and_opposite_grade_directions_only_use_versioned_rules`：一级证书对精确二级candidate，对有来源字典的at_least才confirmed；matching.`test_exact_or_and_not_unknown_are_evaluated_without_lossy_prefilter`同样验证 | 隔离算法 |
| 同类OR、跨类AND | matching同方法：电子一级或二级，且ITSS二级，返回confirmed；condition_id完整保留must.0.0/.0.1/.1 | 隔离ORM适配+规则 |
| 不同等级方向、字典版本 | conditions上述方法：ITSS一级及以上二级成立，CS三级及以上二级成立，缺来源/错误版本/空关系未知；matching.`test_source_version_direction_and_disabled_rule_are_enforced`、`test_rule_applicability_and_certificate_standard_do_not_silently_fallback`拒绝禁用/日期/标准错配 | 隔离算法+数据库规则 |
| NOT未知、冲突逻辑 | conditions.`test_all_four_values_and_boolean_short_circuit_rules`覆盖failed/conflict/unknown/satisfied及NOT；matching同OR方法对NOT未支持类别candidate | 隔离算法 |
| 未支持类别不满足、禁止任意SQL/字段 | conditions.`test_strict_bounded_language_rejects_instructions_and_orm_paths`拒绝ORM路径、raw_sql、SQL字段等；assistant.`test_model_sql_and_fabricated_source_are_rejected_before_matching`断言failed且无快照 | 隔离服务 |

等级字典测试采用明确标注的虚构依据验证方向；当前正式未支持的关系继续unknown，不等于已证实所有资质允许该方向。[D23实际两文件](2026-10-18-real-grade-relation-docx.md)、[GM新裸默认/及以上文件](2026-10-18-gm-file-default-range-native.md)补的是AI提取与自身引用，不替代真实证书核验。

## AI-AC06/07：主体、硬失败与时点

| 子句 | 实质对应 | 限制 |
| --- | --- | --- |
| 集团/厂商/个人不能替投标人；范围不符 | matching.`test_parent_manufacturer_person_product_and_scope_cannot_confirm_bidder`逐项改holder_company_id/holder_type/holder_name/scope，每项candidate；conditions.`test_confirmed_requires_subject_evidence_dates_and_active_status`以confirmed作对照 | 虚构企业隔离样本，符合AC06输入口径 |
| 明确硬失败排除并保留依据 | matching.`test_verified_province_hard_failure_is_excluded_despite_satisfied_preference`及日期例中的每项evidence_id；conditions.`test_missing_or_failed_certificate_is_not_exhaustive_absence`先candidate，存在同日同主体完整类别核查依据才excluded | 单条过期/他级证书不是“企业没有其他合格证书”，不能因此直接排除 |
| 将到期/已到期/未生效/缺起止/撤销 | matching.`test_inclusive_date_boundaries_missing_dates_and_revocation_keep_citations`：当天始止confirmed；昨日结束/明日生效/缺值/revoked/suspended/unknown均candidate，evidence_id仍在逐项依据；assistant.`test_matching_requires_current_evidence_not_legacy_present`有30天后到期的正对照 | 不编造撤销事实 |
| 今天有效不保证投标日有效 | integration_review.`test_revocation_evidence_must_address_the_requested_date`：今天confirmed，前后10天candidate；追加明确historical revocation_as_of后历史日期confirmed | 有真实正反例，不只是判断最终候选数 |
| 未来取得或检查时点不一致不算有效 | matching.`test_future_evidence_and_inconsistent_check_date_never_verify`及`test_query_and_tender_dates_require_actual_revocation_check_at_that_date`均candidate | 不把checked_today替代指定时点 |

## AI-AC08：分类、零确认与显式放宽

分类正对照为conditions.`test_confirmed_requires_subject_evidence_dates_and_active_status`；冲突同方法直接断言verdict=conflict，NOT/AND/OR传播另有测试。matching.`test_unknown_companies_remain_and_lexicographic_preferences_sort_stably`保留3个未知企业，并验证排序稳定；`test_verified_province_hard_failure_is_excluded_despite_satisfied_preference`证明优先项不抵消硬失败。逐条件ID及证据由matching的OR与日期测试断言。

file_conditions共有19个当前测试方法：明确类别/全部取消、保留用户文字与旧快照、剩余为空澄清、未命中/未知类别、OR/NOT澄清、否定、附件注入、模型授权字段拒绝、pending附件同owner/cid、失败恢复，以及多轮平坦去重。`test_many_real_followups_keep_flat_deduplicated_file_requirements`是隔离真正多轮worker流程，其“real”不是外部真实模型。source_guard补混合文字自身message引用、旧未定位guard及旧checkpoint不提升；relation_guard补关系出处、不凭其他类别“及以上”扩大。

真实PDF/表格/扫描和GM文字快照均1283候选、0确认，原声明未升级。worker当前回复写“已检索当前授权库：已确认…待核实…排除…”，只有总在库0时追加“不能据此判断市场不存在”。未知明细含逐项缺口；本审阅**没有找到“非空候选而零确认”整体文案解释范围/缺口的专用断言**。建议最小隔离测试检查真实response/message加results的组合呈现，再由root判断AC08完整语义是否足够，不额外模型。

## AI-AC09：查询零外发与独立研究

query_research_policy在setUp把旧研究/事实写开关全开，并把独立研究的 `run_query_research/_research_company/search_public_query/fetch_public_page/generate_for_use` 全设调用即失败的守卫。7个方法覆盖普通文字、关闭研究开关仍正常、仅文件、追问+导出、legacy partial关联retry、已有快照恢复、独立manifest仍可执行。每次查询断言守卫未调用、Company完全不变、无ResearchManifest/Evidence/FactRevision，快照not_requested、checkpoint independent_manifest_only。条件理解模型stub与研究模型守卫分开，不能说普通查询0模型。

research_runtime的网络OSError实测为**stub异常**：3次后inaccessible，缓存复用不再读；TLS stub1次即停；缺search配置仍尝试已知官网；模型造quote/source_id不产生事实；来源存储hash变更拒绝；reader不补主字段。facts补矛盾值与错主体不写。research报告将inaccessible尝试、完成尝试、verified分开。

缺口：现有测试不是“真实公网慢网”计时，也未找到同一独立manifest同时注入慢搜索+正文不可读+相互冲突来源并断言旧snapshot完全不变的单独用例。普通查询无需公网这一边界可单独提审；独立故障的完整组合另列最小隔离用例，不以非空RSS或一次发现覆盖替代质量门禁。

## AI-AC12：导出逐句与证号缺口

exports.`test_default_confirmed_selection_three_sheets_text_types_and_source_locator`用openpyxl真实读生成ZIP/XLSX，三表名、结果行数、逐项证据URL/page、phone `00123456789`、credit_code `001234567890123456`及每个非空cell.data_type=s/nohyperlink实际断言；`=HYPERLINK/+/@`字符串不成为公式。`test_explicit_candidates_separate_limit_and_fields_apply`测候选单独表、limit及fields；`test_empty_snapshot_generates_headers_without_fake_companies`断言0及仅标题；`test_missing_snapshot_fields_remain_blank_and_new_revision_cannot_change_old_file`新增后续结果revision再逐字节读取旧文件相等。幂等、过期、hash破坏、lease/fence崩溃发布与HTTP重试另有测试。两真实角色现有候选/默认0确认文件GET下载和读回见[已有会话恢复](../AI-T13/2026-10-17-night-readonly-recovery.md)，不声称真实有确认企业。

**当前条件OUTPUT_FIELDS仅name/province/city/website/phone/email/credit_code/address，exports三表无专门certificate_no列；fixture的证号 `001239`只在facts的证书落库测试，不是Excel读回。** 因此“证号前导零保留”还不能引用电话/信用代码测试替代。root可选择最小增量：逐项依据输出对应证书号并用真实XLSX读回断言，或明确原规格证号输出范围后再判断；本单位不擅改业务代码或验收标准。

## AI-AC14：权限边界

| 必须结果 | 已有直接断言 | 最小待证 |
| --- | --- | --- |
| 共享企业不共享私人聊天、跨owner/scope | assistant.`test_owner_scope_and_refresh_recovery_are_checked_on_each_read`对他人conversation/job/发送404，异scope会话404；integration_review.`test_snapshot_owner_scope_and_revision_boundaries`禁止他人/异scope保存快照；exports所有者/异scope404 | 尚未找到所有新路由逐一覆盖reader/维护/无权/他人/异scope的穷举表 |
| reader不写事实/研究需维护 | jobs.`test_readonly_query_and_export_allowed_research_requires_maintenance`；facts.reader proposal保持主值；research.maintenance ownership scope；reviewed_enrichment reader/revoked/stale拒绝 | 普通查询始终0研究有更强守卫，不必外发证书 |
| 撤权终止后续写入 | jobs.`test_revoked_permission_persists_failed_without_publishing_checkpoint`把研究任务置failed/permission_revoked、checkpoint未写/lease清，queued撤账号不能claim；facts拒绝旧user；matching拒绝撤销stale对象；legacy锁后再次fresh权限 | 不是每个新API都在请求前/流式下载进行中实际撤销的完整矩阵；标准要求下载请求前重校验与已发流撤回要区分 |
| 撤权禁止下载与统一响应 | exports.`test_owner_scope_revocation_expiry_and_cleanup_are_enforced`撤读权不能open_export；HTTP他人下载404；integration_review malformed storage refs统一not_found | 无读权本来403、他人/未知404是既有约定，不能强改所有403为404；需对照各入口既定约定补表 |

## AI-AC15：防护覆盖与未覆盖边界

已直接断言：条件白名单/上限/SQL不执行；附件magic伪装、旧doc与DOCX `../escape.xml`拒绝；跨会话附件拒绝；file_conditions附件注入不能取消硬要求；source_guard伪造message/外人附件引用拒绝；relation_guard其他类别/否定/错主体不能授权等级扩大；Bing RSS固定端点、DTD/实体、深度/响应大小/私网literal和DNS、凭据/端口/控制字符、redirect/TLS/timeout/预算及代理边界；XLSX全部非空字符串类型、无hyperlink；public evidence locator与私有storage/import_ref脱敏；白名单Gateway timeout message不带上游全文。

这些是具体层的结果，不等于安全全句完成：测试名包含 `format_bomb` 但正文只造了路径穿越ZIP，没有实际高压缩比炸弹；网页正文恶意指令是否无法改变工具/任务权限、恶意Markdown在真实当前组件是否保持纯文本，以及日志不包含整段私密文档，尚缺直接攻击载荷及断言。搜索只带公开公司名、不带内部字符串有stub断言，而当前普通查询0搜索守卫更强；不能因此声称独立研究所有潜在参数都经过实际泄漏检测。最小后续应为合成载荷、隔离storage/DB/假provider与日志capture，不需新模型、外网或前端修改。

## 下一步

建议root先审AI-AC05/06/07及AI-AC10的整项放行口径；逐项确认是否接受历史测试源指纹限度，必要时只重跑对应模块。AI-AC12证号输出、AI-AC08零确认完整解释、AI-AC14逐入口与AI-AC15攻击载荷是可通过后端隔离最小单元解决的候选；物理低置信OCR与真正无blur运行环境继续保持真实缺口。AI-AC19全库字段/证书核实和AI-AC18远程范围不能借上述建议提前完成。

本文没有提出新的真实模型调用预算，也没有把夜间用户“没有额外模型预算”理解成取消技术幂等、超时和有限重试。
