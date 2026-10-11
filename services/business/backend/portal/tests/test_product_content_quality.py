from django.test import SimpleTestCase

from portal.product_content_quality import (
    content_review_prompt,
    content_quality_policy_hash,
    generation_quality_rules,
    inspect_content_quality,
    inspect_chapter_contract,
    inspect_repeated_content,
    project_fact_text,
    unsupported_numeric_claims,
)


FACTS = {
    "project": "合成数据平台建设项目",
    "background": "项目位于西安，拟统一三套内部业务系统的数据采集、存储和质量监控。业务系统数量：3套。现有数据服务器数量：2台。",
    "items": [{"name": "数据服务器", "quantity": 2, "unit": "台"}],
    "conditions": ["在现有机房部署", "支持权限控制和审计", "预算和工期待确认"],
}


class ProductContentQualityTests(SimpleTestCase):
    def inspect(self, *paragraphs, facts=FACTS, references=None):
        return inspect_content_quality(paragraphs, project_facts=facts, source_context=references)

    def test_explanatory_verification_path_is_not_a_record_quota(self):
        actual = ("本章目标定义的可检验性还需补充一条约束验证路径：蓝图给出的三个建设方向——"
                  "统一采集、统一存储、统一质量监控——各自成立的前提条件不同，"
                  "其验证方法也应分别设计而非套用同一模板。")
        self.assertEqual(self.inspect(actual), [])
        self.assertEqual(unsupported_numeric_claims([actual], project_facts=FACTS), [])
        for text in ("项目仅保留一条记录。", actual + "记录大小为8GB。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
        self.assertTrue(self.inspect("项目仅保留一条记录。", facts=actual))

    def test_sibling_report_arguments_do_not_transfer_allocation_to_server_total(self):
        facts = "项目涉及三套内部业务系统，现有两台数据服务器。"
        first = "数据源接口清单（记录每套系统的接口类型、协议、认证方式、字段结构及历史数据量级）"
        actual = ("调查发起方应为本项目技术负责人，调查产出物包括三份独立文档：" + first
                  + "、服务器资源报告（记录两台数据服务器的硬件配置、当前负载、剩余容量及网络互联拓扑）"
                    "、质量管控现状记录（记录各系统已有的质量检查项、告警方式、历史问题频率及业务方对合格性的定义）。")
        self.assertEqual(self.inspect(actual, facts=facts), [])
        self.assertEqual(unsupported_numeric_claims([actual], project_facts=facts), [])
        for noun in ("每套系统配置两台数据服务器", "财务系统的两台数据服务器",
                     "两台认证服务器", "新增两台数据服务器"):
            with self.subTest(noun=noun):
                text = first + "、服务器资源报告（记录" + noun + "的硬件配置）。"
                self.assertTrue(self.inspect(text, facts=facts))
        # Current and containing ownership survives the sibling-node boundary.
        for owner in ("每套系统", "财务系统"):
            with self.subTest(owner=owner):
                text = owner + "的调查产出包括：" + first + "、服务器资源报告（记录两台数据服务器）。"
                self.assertTrue(self.inspect(text, facts=facts))

    def test_reported_inventory_count_preserves_value_owner_use_and_source_polarity(self):
        facts = "项目涉及三套内部业务系统，现有两台数据服务器。"
        actual = "其中数据服务器数量沿用项目已提供的两台事实。"
        self.assertEqual(self.inspect(actual, facts=facts), [])
        self.assertEqual(unsupported_numeric_claims([actual], project_facts=facts), [])
        for text in ("其中数据服务器数量沿用项目已提供的三台事实。",
                     "其中财务系统的数据服务器数量沿用项目已提供的两台事实。",
                     "其中每套系统的数据服务器数量沿用项目已提供的两台事实。",
                     "其中认证服务器数量沿用项目已提供的两台事实。",
                     "其中新增数据服务器数量沿用项目已提供的两台事实。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=facts))
        negative = "项目涉及三套内部业务系统。其中数据服务器数量不得沿用项目已提供的两台事实。"
        self.assertTrue(self.inspect("现有两台数据服务器。", facts=negative))
        self.assertTrue(unsupported_numeric_claims(["现有2台数据服务器。"], project_facts=negative))
        positive = "财务系统的两台数据服务器。"
        self.assertEqual(self.inspect(positive, facts=positive), [])
        self.assertEqual(self.inspect("其中财务系统的数据服务器数量沿用项目已提供的两台事实。",
                                      facts=positive), [])

    def test_postposed_unset_predicate_only_qualifies_its_parameter_argument(self):
        actual = ("由于缺乏历史负载数据，具体的延迟阈值（如秒级或分钟级）无法预先设定，"
                  "需在试运行期间根据业务容忍度协商确定。")
        self.assertEqual(self.inspect(actual), [])
        self.assertTrue(self.inspect(actual + "本项目响应时间为90毫秒。"))
        self.assertTrue(self.inspect("本项目延迟阈值为秒级。", facts=actual))
        self.assertTrue(self.inspect("方案无法预先确定，平台固定秒级延迟阈值。"))
        confirmed = "本项目延迟阈值为90毫秒。"
        self.assertEqual(self.inspect(confirmed, facts=confirmed), [])

    def test_nominal_parameter_setting_missing_basis_is_not_adopted_frequency_evidence(self):
        actual = ("由于当前资料未提供具体的业务中断恢复时间目标（RTO）或数据新鲜度要求，"
                  "任何关于“每小时”、“每日”或具体分钟数值的设定均缺乏项目依据，列为待确认项。")
        self.assertEqual(self.inspect(actual), [])
        for text in ("备份固定每小时增量和每日全量。", actual + "同步固定每小时执行。",
                     "备份固定每周全量。" + actual, "数据规模缺乏项目依据，备份固定每日全量。",
                     "本项目已采用“每小时”同步。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=actual))

    def test_hash_algorithm_identifiers_only_qualify_the_complete_lexical_token(self):
        field = "校验算法（如MD5、SHA256）"
        self.assertEqual(self.inspect(field), [])
        self.assertEqual(unsupported_numeric_claims([field], project_facts=FACTS), [])
        for text, value in (("使用MD5核查数据，记录大小为5GB。", "5"),
                            ("使用SHA256核查数据，响应时间为256毫秒。", "256"),
                            ("MySHA256Client不能替代经核验的算法。", "256")):
            with self.subTest(text=text):
                self.assertEqual([p["parameter"] for p in unsupported_numeric_claims([text], project_facts=FACTS)], [value])

    def test_attributed_component_version_needs_the_same_positive_uploaded_reference(self):
        text = "Apache Kafka官方文档指出Connect框架自3.3.0版本起支持exactly-once语义。"
        reference = ("标题：Apache Kafka 3.5：Kafka Connect User Guide\n"
                     "核实结论：源连接器框架支持自3.3.0起提供，且要求分布式模式及启用相应配置。")
        self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS, source_context=reference), [])
        for source in (None, "Apache Kafka Connect 3.5版本。",
                       "Apache Kafka官方文档：Connect框架并非自3.3.0版本起提供支持。"):
            with self.subTest(source=source):
                self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS, source_context=source))
        other = "PostgreSQL框架自3.3.0版本起提供支持。"
        self.assertTrue(unsupported_numeric_claims([other], project_facts=FACTS, source_context=reference))
        self.assertEqual([p["parameter"] for p in unsupported_numeric_claims([text + "日志保留期为3.3天。"],
                         project_facts=FACTS, source_context=reference)], ["3.3"])

    def test_adjacent_investigation_purpose_is_not_a_confirmed_capability_or_numeric_waiver(self):
        actual = ("在现有机房部署条件下，需核实采集节点与业务系统之间的网络连通性、防火墙策略及带宽余量，"
                  "确保传输通道满足预期吞吐需求。")
        self.assertEqual(self.inspect(actual), [])
        affirmative = "本项目位于现有机房，确保传输通道满足预期吞吐需求。"
        for text in (actual + "本项目已保证高可用。", actual + "本项目响应时间为90毫秒。",
                     affirmative, "需核实当前网络。" + affirmative,
                     "需核实当前网络，现有传输通道已确保满足预期吞吐需求。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=actual))
        self.assertEqual(self.inspect(affirmative, facts=affirmative), [])

    def test_arbitrary_single_retry_quantifies_instances_without_authorising_a_retry_quota(self):
        actual = ("判定条件为任意一次失败重试均不产生脏数据，"
                  "且所有异常路径均有对应的告警通知与人工介入流程。")
        self.assertEqual(self.inspect(actual), [])
        self.assertTrue(self.inspect(actual + "失败后自动重试1次。"))
        self.assertTrue(self.inspect("失败后自动重试一次。", facts=actual))

    def test_arbitrary_single_record_is_universal_and_does_not_qualify_capacity_or_inventory(self):
        actual = ("判定条件为任意一条记录均可回溯至其最初的采集时刻与源系统表行，"
                  "且在经过多次转换后仍保持标识唯一性。")
        self.assertEqual(self.inspect(actual), [])
        self.assertTrue(self.inspect("任意一条记录大小为8GB。"))
        self.assertTrue(unsupported_numeric_claims(["任意一条记录大小为8GB。"], project_facts=FACTS))
        self.assertTrue(self.inspect("项目仅保留一条记录。", facts=actual))

    def test_percentile_field_names_do_not_authorise_actual_latency_or_reliability(self):
        field = "接口响应时间P95/P99分位数"
        self.assertEqual(self.inspect(field), [])
        self.assertEqual(unsupported_numeric_claims([field], project_facts=FACTS), [])
        for text in ("P95=95毫秒。", field + "；可靠性99%。", "响应时间为95毫秒。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=field))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=field))

    def test_frequency_examples_with_local_missing_basis_do_not_authorise_fixed_schedules(self):
        field = "同步周期的具体数值（如每日或每周）缺少项目依据"
        actual = (field + "，需根据安全风险评估结果确定，"
                  "高风险场景宜采用实时同步，低风险场景可接受延迟同步。")
        self.assertEqual(self.inspect(actual), [])
        for text in (field + "但备份固定每日全量且响应时间为90毫秒。",
                     "备份固定每日全量和每周全量。", "设备缺少项目依据，备份固定每日全量。",
                     "获取方法为部署探针并运行至少一周，收集基线数据以排除启动初期的波动干扰。",
                     "预测未来三年增长趋势下的成本变化曲线。", "判定条件为能在秒级返回关联日志。",
                     "备份固定每周全量和每日增量。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=actual))

    def test_business_recovery_goals_are_not_written_from_measured_test_results(self):
        actual = ("所有关于主备同步延迟、故障恢复时间目标（RTO）及恢复点目标（RPO）的数值，"
                  "均需在实际压力测试后根据实测结果填写，严禁在无依据情况下承诺秒级或分钟级指标。")
        self.assertEqual([issue["code"] for issue in self.inspect(actual)], ["technical_concept_mismatch"])
        wrong = "RTO目标根据实测结果填写。"
        self.assertEqual(self.inspect("不应将" + wrong), [])
        self.assertEqual([issue["code"] for issue in self.inspect("不应将" + wrong + wrong)],
                         ["technical_concept_mismatch"])
        self.assertEqual(self.inspect("RTO目标由业务确认，主备同步延迟根据实测结果填写。"), [])
        self.assertEqual(self.inspect("RTO和RPO目标由业务确认，恢复演练验证实际耗时和可恢复数据位置是否满足目标。"), [])

    def test_keepalived_network_takeover_is_distinct_from_database_role_management(self):
        actual = "首先，调查现有服务器是否已安装数据库集群管理工具（如Patroni、Keepalived等）及其配置状态；"
        self.assertEqual([issue["code"] for issue in self.inspect(actual)], ["technical_concept_mismatch"])
        correct = "Keepalived不是数据库集群管理工具，仅用于网络入口接管及健康检查。"
        self.assertEqual(self.inspect(correct), [])
        self.assertEqual([issue["code"] for issue in self.inspect(correct + "Keepalived是数据库集群管理工具。")],
                         ["technical_concept_mismatch"])
        self.assertEqual(self.inspect("数据库复制与主备角色管理、健康检查和虚拟IP接管须分别核查，具体工具和配置待确认。"), [])

    def test_sql_audit_candidates_keep_privacy_minimisation_in_generation_and_review(self):
        self.assertEqual(self.inspect("可评估SQL模板、操作类型和行数审计，字段范围及敏感内容排除规则待确认。"), [])
        correct = ("审计字段按最小必要原则分类确认，不默认记录原始SQL参数或查询结果；"
                   "密码、访问令牌、密钥等凭据应排除，敏感字段按已确认规则最小化或脱敏。")
        self.assertEqual(self.inspect(correct), [])
        for rules in (generation_quality_rules(), content_review_prompt()):
            for marker in ("最小必要", "原始SQL参数", "访问令牌", "密钥", "凭据应排除", "可信锚点", "权限隔离"):
                self.assertIn(marker, rules)

    def test_hash_chain_explicit_anchor_denial_is_local_and_preserves_conditional_detection(self):
        wrong = "哈希链无需可信锚点即可保障完整性。"
        self.assertEqual([issue["code"] for issue in self.inspect(wrong)], ["technical_concept_mismatch"])
        self.assertEqual(self.inspect("不能断言" + wrong), [])
        self.assertEqual([issue["code"] for issue in self.inspect("不能断言" + wrong + wrong)],
                         ["technical_concept_mismatch"])
        self.assertEqual([issue["code"] for issue in self.inspect("已保存受保护的可信基准。" + wrong)],
                         ["technical_concept_mismatch"])
        self.assertEqual(self.inspect("在受保护的可信锚点及校验基准条件下，可评估哈希链用于完整性检测，项目适用性待确认。"), [])

    def test_defined_threshold_trigger_does_not_approve_its_fixed_values(self):
        chinese = ("判定条件设定为：当任一资源指标持续超过安全阈值"
                   "（如CPU使用率连续五分钟高于百分之八十）时，视为瓶颈出现。")
        arabic = chinese.replace("五分钟", "5分钟").replace("百分之八十", "80%")
        for statement, parameters in ((chinese, ["五分钟", "百分之八十"]),
                                      (arabic, ["5分钟", "80%"]),
                                      ("告警规则规定为：当CPU使用率连续六分钟超过75%时，发送告警。",
                                       ["六分钟", "75%"])):
            with self.subTest(statement=statement):
                self.assertEqual([issue.get("parameter") for issue in self.inspect(statement)], parameters)
                self.assertEqual(self.inspect(statement, facts=statement), [])
        self.assertEqual([issue["parameter"] for issue in
                          unsupported_numeric_claims([arabic], project_facts=FACTS)], ["5", "80"])
        self.assertEqual([issue.get("parameter") for issue in
                          self.inspect(chinese + "响应时间为90毫秒。")],
                         ["五分钟", "百分之八十", "90毫秒"])
        for candidate in ("若CPU使用率连续五分钟高于百分之八十，则记录负载情况供调查确认。",
                          "候选判定条件待确认：当CPU使用率连续五分钟高于百分之八十时，记录负载情况。"):
            self.assertEqual(self.inspect(candidate), [])
        for source in (chinese.replace("设定为", "不得设定为"), "若采用" + chinese,
                       "候选判定条件待确认：当CPU使用率连续五分钟高于百分之八十时，视为瓶颈出现。"):
            with self.subTest(source=source):
                self.assertEqual([issue.get("parameter") for issue in self.inspect(chinese, facts=source)],
                                 ["五分钟", "百分之八十"])

    def test_denied_assertion_is_local_and_never_positive_source_evidence(self):
        actual = ("由于本项目尚未选定具体的消息队列组件或流处理引擎，且未确认业务系统是否支持"
                  "CDC（变更数据捕获）或增量日志读取，因此不能断言数据在传输过程中必然无丢失或无重复。")
        self.assertEqual(self.inspect(actual), [])
        denied = "本项目不能断言数据在传输过程中必然无丢失或无重复。"
        self.assertEqual(self.inspect(denied), [])
        self.assertEqual([issue.get("parameter") for issue in
                          self.inspect("本项目不能断言数据必然无丢失且响应时间为90毫秒。")], ["90毫秒"])
        self.assertEqual([issue["code"] for issue in
                          self.inspect("本项目不能断言数据必然无丢失，但本项目数据传输必然无重复。")],
                         ["unsupported_capability_claim"])
        positive = "本项目数据在传输过程中必然无丢失或无重复。"
        self.assertTrue(self.inspect(positive, facts="不能断言" + positive))
        self.assertEqual(self.inspect(positive, facts=positive), [])
        numeric = "响应时间为90毫秒。"
        self.assertTrue(self.inspect(numeric, facts="不能断言" + numeric))
        self.assertTrue(unsupported_numeric_claims([numeric], project_facts="不能断言" + numeric))
        self.assertEqual(self.inspect(numeric, facts="不能断言" + positive + numeric), [])

    def test_explicit_conflict_case_quota_is_distinct_from_report_or_test_steps(self):
        statement = ("验收证据应包含一份元数据差异分析报告，列出至少十个典型冲突案例及其潜在影响范围，"
                     "为后续清洗逻辑设计提供依据。")
        self.assertEqual([issue.get("parameter") for issue in self.inspect(statement)], ["十个"])
        self.assertEqual([issue.get("parameter") for issue in self.inspect(statement.replace("十个", "10个"))],
                         ["10个"])
        self.assertEqual(self.inspect(statement, facts="验收应列出至少十个典型冲突案例。"), [])
        for source in ("验收应至少部署十个节点。", "是否需列出至少十个典型冲突案例待确认。",
                       "没有十个典型冲突案例。"):
            self.assertTrue(self.inspect(statement, facts=source))
        self.assertEqual(self.inspect("列出至少十个典型冲突案例的要求待确认。"), [])
        self.assertEqual(self.inspect("验收应包含一份报告，至少一次测试并逐项记录核查结论。"), [])

    def test_schema_registry_is_not_a_generic_connect_exactly_once_requirement(self):
        actual = ("Kafka Connect等框架虽支持恰好一次处理语义，但其适用性高度依赖于"
                  "Connector类型、Schema注册中心配置及幂等性实现。")
        self.assertEqual([issue["code"] for issue in self.inspect(actual)], ["technical_concept_mismatch"])
        self.assertEqual([issue["code"] for issue in self.inspect(
            "虽然Kafka Connect等框架在特定配置下支持恰好一次处理语义，但这并非默认能力，"
            "而是高度依赖于Connector的具体实现、Schema注册中心的兼容性策略以及生产者的幂等性配置。")],
            ["technical_concept_mismatch"])
        self.assertEqual(self.inspect("Kafka Connect恰好一次需核验连接器、模式与配置，"
                                      "Schema注册中心的兼容策略属于独立的数据契约检查。"), [])
        self.assertEqual(self.inspect("不能断言Kafka Connect恰好一次能力高度依赖于Schema注册中心。"), [])

    def test_oauth_authorization_cannot_be_classified_as_identity_authentication(self):
        actual = ("然而，资料未提供现有的身份认证协议（如LDAP、OAuth2.0）或用户目录结构，"
                  "因此无法直接集成现成的认证中心。")
        self.assertEqual([issue["code"] for issue in self.inspect(actual)], ["technical_concept_mismatch"])
        self.assertEqual([issue["code"] for issue in self.inspect("OAuth2.0是身份认证协议。")],
                         ["technical_concept_mismatch"])
        for correct in ("OAuth2.0是授权框架，身份认证流程与用户目录须另外核实。",
                        "不能断言OAuth2.0是身份认证协议。", "“OAuth2.0是身份认证协议”这一说法错误。"):
            self.assertEqual(self.inspect(correct), [])
        self.assertTrue(self.inspect("OAuth2.0是身份认证协议。", facts="OAuth2.0不是身份认证协议。"))

    def test_authentication_example_exclusion_is_bound_only_to_its_oauth_term(self):
        actual = "需核查身份认证协议（如OIDC，不包括OAuth2.0）。"
        for exclusion in ("不包括", "不含", "排除"):
            with self.subTest(exclusion=exclusion):
                self.assertEqual(self.inspect(actual.replace("不包括", exclusion)), [])
        for text in (actual + "OAuth2.0是身份认证协议。",
                     actual[:-1] + "，但OAuth2.0是身份认证协议。",
                     "需核查身份认证协议（不包括LDAP，如OAuth2.0）。"):
            with self.subTest(text=text):
                self.assertEqual([issue["code"] for issue in self.inspect(text)], ["technical_concept_mismatch"])
        self.assertEqual([issue.get("parameter") for issue in
                          self.inspect(actual + "响应时间为90毫秒。")], ["90毫秒"])

    def test_corrected_authentication_example_keeps_later_wrong_classification_checked(self):
        corrected = "身份认证协议（如LDAP、OAuth2.0）这一表述不准确，应将OAuth2.0归为授权框架。"
        self.assertEqual(self.inspect(corrected), [])
        self.assertEqual([issue["code"] for issue in
                          self.inspect(corrected + "OAuth2.0是身份认证协议。")], ["technical_concept_mismatch"])

    def test_log_hash_evidence_does_not_independently_guarantee_tamper_protection(self):
        actual = ("验证证据应包括权限变更的操作日志、越权访问尝试的拦截记录以及审计日志本身的"
                  "完整性校验哈希值，确保日志未被恶意篡改。")
        self.assertEqual([issue["code"] for issue in self.inspect(actual)], ["technical_concept_mismatch"])
        self.assertEqual(self.inspect("日志完整性校验哈希值须与受保护的可信基准比较，"
                                      "不能仅凭哈希值确保日志未被恶意篡改。"), [])
        self.assertEqual(self.inspect("本项目不能断言仅凭哈希值确保日志未被恶意篡改。"), [])

    def test_log_hash_check_binds_its_own_protected_isolated_trusted_baseline(self):
        actual = "以独立隔离且受保护的可信基准核验审计日志完整性校验哈希值，确保日志未被恶意篡改。"
        self.assertEqual(self.inspect(actual), [])
        self.assertEqual(self.inspect("用隔离且受保护的可信校验基准比对审计日志的完整性校验哈希值，"
                                      "确保日志未被恶意篡改。"), [])
        unsupported = "审计日志完整性校验哈希值，确保日志未被恶意篡改。"
        for text in ("已保存独立隔离且受保护的可信基准。" + unsupported,
                     "已保存独立隔离且受保护的可信基准，收集" + unsupported,
                     "未" + actual, "拟" + actual,
                     actual.replace("隔离且受保护", "隔离但不受保护"),
                     "以独立隔离且受保护的可信基准核验审计日志，仅凭普通哈希值确保日志未被恶意篡改。"):
            with self.subTest(text=text):
                self.assertEqual([issue["code"] for issue in self.inspect(text)], ["technical_concept_mismatch"])

    def test_missing_marker_does_not_make_full_comparison_the_only_generic_path(self):
        actual = ("若源系统为传统关系型数据库，需核实其版本是否支持增量标记字段"
                  "（如更新时间戳或自增ID），这是实现高效增量同步的前提。"
                  "若缺乏此类字段，则全量比对将成为唯一可行方案，但这会显著增加计算负载和网络压力，"
                  "必须在后续容量评估中作为高风险项对待。")
        self.assertEqual([issue["code"] for issue in self.inspect(actual)], ["technical_concept_mismatch"])
        self.assertEqual(self.inspect("若缺少更新时间戳或自增ID，应另行核查日志CDC和变更事件；"
                                      "全量比对可以作为待评估的备选。"), [])
        self.assertEqual(self.inspect("不应声称若缺少标记字段，则全量比对将成为唯一可行方案。"), [])

    def test_rules_require_mechanism_evidence_for_the_reviewed_concept_boundaries(self):
        for rules in (generation_quality_rules(), content_review_prompt()):
            for marker in ("观察窗口", "Schema注册中心", "OAuth2.0", "可信校验基准", "自增标识",
                           "RTO", "RPO", "冷热分层", "I/O", "业务真值", "有效性"):
                self.assertIn(marker, rules)

    def test_specific_business_system_is_a_complete_generic_count_alias(self):
        facts = "项目涉及三套内部业务系统，现有两台数据服务器。"
        text = "通常涵盖完整性、准确性、一致性和及时性四个维度，但针对本项目的三套特定业务系统，哪些维度具有最高优先级尚不明确。"
        self.assertEqual(self.inspect(text, facts=facts), [])
        self.assertEqual(self.inspect("项目涉及3套业务系统。", facts="项目涉及三套特定业务系统。"), [])
        for wrong in (text.replace("三套", "四套"), text.replace("特定业务系统", "财务业务系统"),
                      text.replace("特定业务系统", "业务系统A"), "每套特定业务系统配置两台服务器。"):
            with self.subTest(text=wrong):
                self.assertTrue(self.inspect(wrong, facts=facts))
        for negative in ("项目不存在3套特定业务系统。", "项目没有三套特定业务系统。"):
            with self.subTest(facts=negative):
                self.assertTrue(self.inspect("项目涉及3套业务系统。", facts=negative))
                self.assertEqual([i["parameter"] for i in unsupported_numeric_claims(
                    ["项目涉及3套业务系统。"], project_facts=negative)], ["3"])

    def test_adjacent_system_stop_remainder_uses_the_confirmed_total_minus_one(self):
        for total, remaining in ((3, 2), (5, 4)):
            text = f"当某1套业务系统停机维护时，其他{remaining}套系统的数据流不应受到阻塞。"
            for facts in (f"项目涉及{total}套内部业务系统。", f"业务系统数量为{total}套。"):
                with self.subTest(total=total, facts=facts):
                    self.assertEqual(self.inspect(text, facts=facts), [])
                    self.assertEqual(unsupported_numeric_claims([text], project_facts=facts), [])
        text = "例如，当某一套业务系统停机维护时，其他两套系统的数据流不应受到阻塞，这要求采集组件具备独立进程或线程隔离机制。"
        self.assertEqual(self.inspect(text, facts="项目涉及三套内部业务系统。"), [])
        self.assertEqual(self.inspect("若某一套业务系统停机，其余两套业务系统的数据流不应被阻塞。",
                                      facts="项目涉及三套内部业务系统。"), [])

    def test_system_remainder_relation_rejects_wrong_count_scope_and_assertion(self):
        facts = "项目涉及3套内部业务系统，现有2台数据服务器。"
        for text in (
            "当某1套业务系统停机维护时，其他3套系统的数据流不应受到阻塞。",
            "当至少1套业务系统停机维护时，其他3套系统的数据流不应受到阻塞。",
            "当某1套财务系统停机维护时，其他3套系统的数据流不应受到阻塞。",
            "当某1套业务系统停机维护时，其他3套人事系统的数据流不应受到阻塞。",
            "当某1套业务系统停机维护时，其他3套系统已接入平台。",
            "当某1套业务系统停机维护时，第二阶段扩展至其他3套系统。",
            "其他2套系统的数据流不应受到阻塞。",
        ):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=facts))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))
        scene = "当某1套业务系统停机维护时，其他2套系统的数据流不应受到阻塞。"
        for other_facts in ("现有2台数据服务器。", "项目涉及4套内部业务系统。", "项目涉及3套财务系统。",
                            "每个部门配置3套业务系统。", "项目涉及3套数据系统。", "项目不存在3套业务系统。"):
            with self.subTest(facts=other_facts):
                self.assertTrue(self.inspect(scene, facts=other_facts))
        text = scene + "响应时间为90毫秒。"
        self.assertEqual([i.get("parameter") for i in self.inspect(text, facts=facts)], ["90毫秒"])
        self.assertEqual([i["parameter"] for i in unsupported_numeric_claims([text], project_facts=facts)], ["90"])

    def test_conditional_remainder_sources_do_not_approve_inventory_or_phase(self):
        scene = "当某1套业务系统停机维护时，其他2套系统的数据流不应受到阻塞。"
        for text in ("第二阶段扩展至另外2套系统及质量监控模块。", "其他2套系统已接入平台。",
                     "项目涉及1套业务系统。", "项目涉及2套业务系统。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=scene))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=scene))
        self.assertTrue(self.inspect("第二阶段扩展至另外两套系统及质量监控模块。",
                                    facts="项目涉及三套内部业务系统。" + scene))
        self.assertEqual(self.inspect("响应时间为50毫秒。", facts=scene + "响应时间为50毫秒。"), [])

    def test_system_phase_quantities_require_the_same_approved_phase(self):
        facts = "项目涉及3套内部业务系统。"
        for text in ("第一阶段接入3套业务系统。", "第二阶段扩展至3套系统。", "第三期接入3套业务系统。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=facts))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))
                self.assertEqual(self.inspect(text, facts=text), [])
        self.assertTrue(self.inspect("第二阶段接入3套业务系统。", facts="第一阶段接入3套业务系统。"))
        self.assertTrue(self.inspect("项目涉及3套业务系统。", facts="第一阶段接入3套业务系统。"))
        for source in ("第一阶段不得接入3套业务系统。", "不得在第一阶段接入3套业务系统。",
                       "第一阶段接入3套业务系统待确认。", "若第一阶段接入3套业务系统，则记录验收结果。"):
            with self.subTest(facts=source):
                for body in ("第一阶段接入3套业务系统。", "项目涉及3套业务系统。"):
                    self.assertTrue(self.inspect(body, facts=source))
                    self.assertTrue(unsupported_numeric_claims([body], project_facts=source))
        self.assertEqual(self.inspect("第一阶段核对3套业务系统的接口文档。", facts=facts), [])
        self.assertEqual(self.inspect("第一阶段接入3套业务系统仅为候选且待确认。", facts=facts), [])
        self.assertTrue(self.inspect("旨在解决内部业务系统数据分散、标准不一及质量监控缺失的问题。", facts=facts))

    def test_known_unsourced_chinese_parameters(self):
        for text in (
            "采集最近三个月的数据样本。", "观察期至少一周。",
            "备份策略采用每周全量和每日增量。", "业务允许丢失一小时的数据。",
            "平台实现秒级识别。", "项目需要十万元的投资。", "存储容量为三百GB。",
            "业务允许丢失一个小时的数据。", "观察期为三个工作日。",
        ):
            with self.subTest(text=text):
                self.assertTrue(any(issue["code"] == "unsupported_parameter" for issue in self.inspect(text)))

    def test_server_object_count_descriptors_preserve_known_count_in_either_order(self):
        facts = "项目涉及三套内部业务系统，现有两台数据服务器。"
        for text in (
            "服务器对象数量为两台。", "资料提供服务器对象数量为两台。",
            "资料提供的服务器对象数量为2台。", "数据服务器对象数量为两台。",
            "资料中提供的“数据服务器”对象数量为两台。",
            "上述“两台”为资料中提供的服务器对象数量。",
            "“2台”为现有数据服务器数量。", "‘两台’是清单提供的主机总数。",
            '"两台"为文档提供的"数据服务器"对象数量。',
            "需要明确的是，上述“两台”为资料中提供的服务器对象数量，其具体的物理形态、"
            "网络拓扑结构、各服务器的用途拆分（如是否分别用于热数据处理与冷数据归档）、"
            "主备关系及复制仲裁机制均未在当前资料中提供，属于待确认事项。",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text, facts=facts), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=facts), [])
        self.assertEqual(self.inspect("上述“五台”为资料中提供的服务器对象数量。",
                                      facts="现有五台数据服务器。"), [])

    def test_count_descriptors_do_not_create_server_type_owner_purchase_or_use(self):
        facts = "项目涉及三套内部业务系统，现有两台数据服务器。"
        for text in (
            "认证服务器对象数量为两台。", "上述“两台”为资料中提供的认证服务器对象数量。",
            "上述“两台”为资料中提供的“认证服务器”总数。",
            "上述“两台”为资料中提供的存储设备对象数量。",
            "财务系统的服务器对象数量为两台。",
            "财务系统的“两台”为资料中提供的服务器对象数量。",
            "每套业务系统的服务器对象数量为两台。",
            "每套业务系统的“两台”为资料中提供的服务器对象数量。",
            "新增的“两台”为资料中提供的服务器对象数量。", "采购服务器对象数量为两台。",
            "用于冷数据归档的“两台”为资料中提供的服务器对象数量。",
            "上述“三台”为资料中提供的服务器对象数量。",
            "上述“两台”为资料中提供的“服务器'对象数量。",
            "上述“两台”为资料中提供的服务器对象数量并用于冷数据归档。",
            "第一阶段至少接入一套内部业务系统。", "第二阶段接入其余两套内部业务系统。",
        ):
            with self.subTest(text=text):
                self.assertTrue(any(i["code"] == "unsupported_parameter" for i in self.inspect(text, facts=facts)))

    def test_count_descriptor_sources_keep_polarity_scope_and_local_confirmation(self):
        body = "现有两台数据服务器。"
        positive = "上述“两台”为资料中提供的数据服务器对象数量。"
        self.assertEqual(self.inspect(body, facts=positive), [])
        self.assertEqual(self.inspect("服务器对象数量为两台。", facts=positive), [])
        for source in (
            "上述“两台”并非资料中提供的数据服务器对象数量。",
            "不存在“两台”为资料中提供的数据服务器对象数量。",
            "没有“两台”为资料中提供的数据服务器对象数量。",
            "上述“两台”为待确认的数据服务器对象数量。",
            "上述“两台”为资料中提供的数据服务器对象数量，需确认该数量。",
            "新增的“两台”为资料中提供的数据服务器对象数量。", "新增“两台”数据服务器。",
            "用于冷数据归档的“两台”为资料中提供的数据服务器对象数量。",
            "财务系统的“两台”为资料中提供的数据服务器对象数量。",
            "每套业务系统的“两台”为资料中提供的数据服务器对象数量。",
            "上述“两台”为资料中提供的认证服务器对象数量。",
            "认证服务器对象数量为两台。",
        ):
            with self.subTest(source=source):
                self.assertTrue(self.inspect(body, facts=source))
                self.assertTrue(self.inspect("服务器对象数量为两台。", facts=source))
        for text in ("现有两台认证服务器。", "财务系统配置两台服务器。", "新增两台数据服务器。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=positive))
        self.assertEqual(self.inspect("“2台”为资料中提供的服务器对象数量，需确认该数量。", facts=""), [])
        self.assertTrue(self.inspect("服务器对象数量为两台。", facts="项目规定不得新增“数据服务器”总数为2台。"))

    def test_count_descriptors_leave_following_actual_values_and_status_checked(self):
        facts = "项目涉及三套内部业务系统，现有两台数据服务器。"
        text = "上述“2台”为资料中提供的服务器对象数量，响应时间为90毫秒。"
        self.assertEqual([(i["code"], i.get("parameter")) for i in self.inspect(text, facts=facts)],
                         [("unsupported_parameter", "90毫秒")])
        self.assertEqual([i["parameter"] for i in unsupported_numeric_claims([text], project_facts=facts)], ["90"])
        self.assertTrue(any(i["code"] == "unsupported_project_status" for i in self.inspect(
            "上述“两台”为资料中提供的服务器对象数量，现有系统缺乏统一标准。", facts=facts)))
        text = "“2台”为资料中提供的服务器对象数量，需确认该数量，但响应时间为90毫秒。"
        self.assertEqual([i.get("parameter") for i in self.inspect(text, facts="")], ["90毫秒"])
        self.assertEqual([i["parameter"] for i in unsupported_numeric_claims([text], project_facts="")], ["90"])

    def test_arabic_parameters_and_untyped_configuration(self):
        for text in ("数据保留90天。", "采集周期为30秒。", "存储容量为2TB。",
                     "预算20万元。", "吞吐量达到1000QPS。", "阈值为10。", "端口设置为5432。",
                     "准确率达到百分之九十九。", "响应时间为0.5秒。"):
            with self.subTest(text=text):
                self.assertTrue(any(issue["code"] == "unsupported_parameter" for issue in self.inspect(text)))

    def test_grounded_chinese_and_arabic_quantities(self):
        self.assertEqual(self.inspect("三套内部业务系统的数据采集。", "现有两台数据服务器。",
                                      "现有数据服务器为2台。", "业务系统数量为3套。"), [])

    def test_project_relative_generic_count_keeps_the_counted_noun(self):
        text = "当前已确认的事实包括：项目拟整合的业务系统数量为3套，现有机房部署的数据服务器数量为2台。"
        self.assertEqual(self.inspect(text), [])
        self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
        for facts, count in (("项目涉及三套内部业务系统。", "3"),
                             ("项目涉及四套内部业务系统。", "4")):
            body = "本项目拟整合的内部业务系统数量为" + count + "套。"
            with self.subTest(facts=facts):
                self.assertEqual(self.inspect(body, facts=facts), [])
                self.assertEqual(unsupported_numeric_claims([body], project_facts=facts), [])
                self.assertEqual(self.inspect(count + "套业务系统的数据采集。", facts=body), [])
        for noun in ("财务系统", "HR系统", "源系统A", "资料确认系统"):
            body = "项目拟整合的" + noun + "数量为3套。"
            with self.subTest(noun=noun):
                self.assertTrue(self.inspect(body))
                self.assertTrue(unsupported_numeric_claims([body], project_facts=FACTS))
                self.assertTrue(self.inspect("业务系统数量为3套。", facts=body))
        self.assertTrue(self.inspect("每个部门的项目拟整合的业务系统数量为3套。"))
        self.assertTrue(self.inspect("财务项目拟整合的业务系统数量为3套。"))
        source = "源系统A数量为3套。"
        self.assertEqual(self.inspect(source, facts=source), [])
        self.assertTrue(self.inspect("源系统B数量为3套。", facts=source))

    def test_server_total_predicate_binds_quoted_and_unquoted_nouns(self):
        real = "此外，考虑到仅有一处来源提及“数据服务器”总数为2台，这并不直接证明已具备高可用架构或冷热数据分离能力；"
        self.assertEqual(self.inspect(real), [])
        self.assertEqual(unsupported_numeric_claims([real], project_facts=FACTS), [])
        for noun in ("数据服务器", "“数据服务器”", '"数据服务器"'):
            body = noun + "总数为2台。"
            with self.subTest(noun=noun):
                self.assertEqual(self.inspect(body), [])
                self.assertEqual(unsupported_numeric_claims([body], project_facts=FACTS), [])
                self.assertEqual(self.inspect("数据服务器数量为2台。", facts=body), [])
                combined = body[:-1] + "且响应时间为90毫秒。"
                self.assertEqual([issue["parameter"] for issue in self.inspect(combined)], ["90毫秒"])
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([combined], project_facts=FACTS)], ["90"])

    def test_total_noun_relation_preserves_names_allocations_and_addition_purpose(self):
        for body in ("每套业务系统的“数据服务器”总数为2台。",
                     "财务系统的“数据服务器”总数为2台。", "“交换机”总数为2台。",
                     "“认证服务器”总数为2台。", "“数据服务器”总数为4台。",
                     "认证服务器总数为2台。", "认证数据服务器总数为2台。",
                     "认证的服务器总数为2台。",
                     "新增“数据服务器”总数为2台。"):
            with self.subTest(body=body):
                self.assertTrue(self.inspect(body))
                self.assertTrue(unsupported_numeric_claims([body], project_facts=FACTS))
        for source in ("每套业务系统的“数据服务器”总数为2台。",
                       "财务系统的“数据服务器”总数为2台。", "“交换机”总数为2台。",
                       "认证服务器总数为2台。", "认证数据服务器总数为2台。",
                       "新增“数据服务器”总数为2台。", "“数据服务器”总数不为2台。",
                       "不存在“数据服务器”总数为2台。", "“数据服务器”总数是否为2台待确认。",
                       "未新增“数据服务器”总数为2台。", "不新增数据服务器总数为2台。"):
            with self.subTest(source=source):
                self.assertTrue(self.inspect("数据服务器数量为2台。", facts=source))
                self.assertTrue(unsupported_numeric_claims(["数据服务器数量为2台。"], project_facts=source))
        source = "新增数据服务器总数为2台。"
        self.assertEqual(self.inspect("新增“数据服务器”总数为2台。", facts=source), [])
        self.assertEqual(unsupported_numeric_claims(["新增“数据服务器”总数为2台。"], project_facts=source), [])
        source = "没有扩容安排的项目现有数据服务器总数为2台。"
        self.assertEqual(self.inspect("数据服务器数量为2台。", facts=source), [])
        source = "未新增“数据服务器”总数为2台，但现有数据服务器总数为2台。"
        self.assertEqual(self.inspect("数据服务器数量为2台。", facts=source), [])
        source = "认证服务器总数为2台。"
        self.assertEqual(self.inspect(source, facts=source), [])
        source = "财务系统的数据服务器总数为2台。"
        self.assertEqual(self.inspect("财务系统的2台数据服务器。", facts=source), [])

    def test_forbidden_additions_are_not_positive_quantity_sources(self):
        body = "新增“数据服务器”总数为2台。"
        for negator in ("不得", "不能", "不应", "严禁", "不会"):
            source = "项目规定" + negator + body
            with self.subTest(negator=negator):
                self.assertEqual([issue["code"] for issue in self.inspect(body, facts=source)],
                                 ["unsupported_parameter"])
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([body], project_facts=source)], ["2"])
        self.assertEqual(self.inspect(body, facts=body), [])
        self.assertEqual(unsupported_numeric_claims([body], project_facts=body), [])
        source = "项目规定不得" + body + "现有数据服务器总数为5台。"
        self.assertEqual(self.inspect("数据服务器总数为5台。", facts=source), [])
        self.assertEqual(unsupported_numeric_claims(["数据服务器总数为5台。"], project_facts=source), [])
        self.assertTrue(self.inspect(body, facts=source))
        self.assertEqual([issue["parameter"] for issue in
                          unsupported_numeric_claims([body], project_facts=source)], ["2"])

    def test_different_project_never_inherits_synthetic_test_quantities(self):
        facts = {"background": "业务系统数量：4套。现有数据服务器数量：5台。"}
        self.assertEqual(self.inspect("四套业务系统的数据采集。", "现有五台数据服务器。", facts=facts), [])
        self.assertTrue(self.inspect("三套业务系统的数据采集。", facts=facts))
        self.assertTrue(self.inspect("现有两台数据服务器。", facts=facts))
        self.assertNotIn("三套业务系统、两台服务器", generation_quality_rules())

    def test_nearby_server_does_not_ground_the_quantity_of_a_different_device(self):
        self.assertTrue(self.inspect("现有两台服务器各配两台交换机。"))
        self.assertEqual(self.inspect("现有两台数据服务器。", "数据服务器数量为两台。"), [])

    def test_server_count_binds_to_servers_before_service_description(self):
        for text in (
            "这两台服务器可能分别承担应用服务与数据库服务。",
            "这2台服务器可能分别承担应用服务与数据库服务。",
            "现有数据服务器数量为2台并分别承载财务系统和人事系统。",
            "两台服务器可供财务系统的数据采集使用。",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
        for text in ("两台交换机为服务器提供网络连接。", "两台物理节点承载数据库服务。",
                     "两台节点可能分别承担应用服务与数据库服务。", "服务器采用两个副本。",
                     "这3台服务器可能分别承担应用服务与数据库服务。"):
            with self.subTest(text=text):
                self.assertIn("unsupported_parameter", {issue["code"] for issue in self.inspect(text)})

    def test_server_quantity_keeps_preceding_system_and_department_scope(self):
        for facts, same, other in (
            ("财务系统有两台服务器。", "财务系统的2台服务器承担数据库服务。",
             "人事系统的2台服务器承担数据库服务。"),
            ("财务部门数据服务器数量为2台。", "财务部门两台服务器承担数据库服务。",
             "人事部门2台服务器承担数据库服务。"),
        ):
            with self.subTest(facts=facts):
                self.assertEqual(self.inspect(same, facts=facts), [])
                self.assertEqual(unsupported_numeric_claims([same], project_facts=facts), [])
                for text in (other, "所有业务系统共有2台服务器。", "本项目共有2台服务器。"):
                    self.assertTrue(self.inspect(text, facts=facts))
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))

    def test_project_total_does_not_establish_per_object_server_allocations(self):
        for scope in ("每套业务系统", "每系统", "各业务系统", "每个部门", "各部门", "每个数据库"):
            for number in ("两", "2"):
                text = f"{scope}配置{number}台服务器。"
                with self.subTest(scope=scope, number=number):
                    self.assertIn("unsupported_parameter", {issue["code"] for issue in self.inspect(text)})
                    if number == "2":
                        self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
            self.assertEqual(self.inspect(f"{scope}是否配置两台服务器待确认。"), [])
        self.assertEqual(self.inspect("项目共有两台服务器。", "所有业务系统共用2台服务器。"), [])

    def test_requested_inventory_count_binds_to_noun_instead_of_request_actor(self):
        for prefix in ("向系统集成商索取", "向系统建设单位索取", "向业务系统供应商收集",
                       "请运维部门核对", "要求数据库供应商核对"):
            for number in ("三", "3"):
                text = prefix + number + "套内部业务系统的清单。"
                with self.subTest(prefix=prefix, number=number):
                    self.assertEqual(self.inspect(text), [])
                    self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
        facts = "现有四套内部业务系统。"
        self.assertEqual(self.inspect("向系统建设单位索取4套内部业务系统的架构文档。", facts=facts), [])
        self.assertTrue(self.inspect("向系统建设单位索取3套内部业务系统的架构文档。", facts=facts))

    def test_reported_counter_noun_keeps_generic_named_and_allocation_scope(self):
        for prefix in ("当前资料仅明确了", "现有清单已确认", "文档记载了"):
            for number in ("三", "3"):
                text = prefix + "业务系统数量为" + number + "套。"
                with self.subTest(prefix=prefix, number=number):
                    self.assertEqual(self.inspect(text), [])
                    self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
            for text in (prefix + "财务业务系统数量为3套。",
                         prefix + "HR业务系统数量为3套。",
                         prefix + "业务系统数量为4套。",
                         prefix + "每套业务系统服务器数量为2台。",
                         prefix + "财务部门数据服务器数量为2台。"):
                with self.subTest(prefix=prefix, text=text):
                    self.assertTrue(self.inspect(text))
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
            named = prefix + "财务业务系统数量为三套。"
            self.assertEqual(self.inspect("三套财务业务系统的数据采集。", facts=named), [])
            self.assertTrue(self.inspect("三套业务系统的数据采集。", facts=named))
            per_object = prefix + "每套业务系统服务器数量为两台。"
            self.assertTrue(self.inspect("项目共有2台服务器。", facts=per_object))
            self.assertEqual(self.inspect("每套业务系统配置2台服务器。", facts=per_object), [])
        facts = "业务系统数量为4套。"
        self.assertEqual(self.inspect("当前资料仅明确了业务系统数量为四套。", facts=facts), [])
        # Similar characters inside a system name do not become report prose.
        self.assertTrue(self.inspect("资料确认系统数量为3套。"))
        self.assertEqual(self.inspect("资料确认系统数量为3套。", facts="现有三套资料确认系统。"), [])
        self.assertEqual(self.inspect("三套资料确认系统的数据采集。", facts="现有三套资料确认系统。"), [])
        self.assertTrue(self.inspect("三套业务系统的数据采集。", facts="现有三套资料确认系统。"))
        self.assertEqual(self.inspect("当前资料仅明确了财务系统数量为三套。",
                                      facts="现有三套财务系统。"), [])

    def test_increment_rate_field_qualifies_only_its_statistical_period(self):
        for text in ("明确调查对象包括：各业务系统的数据库类型、表结构元数据、历史数据累积量、每日增量数据速率。",
                     "核对每日增量速率字段。", "收集每小时增量数据速率资料。"):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
        for field in ("每日增量速率", "每日增量数据速率", "每小时增量数据速率"):
            text = field + "为10GB。"
            with self.subTest(field=field):
                self.assertEqual([issue["parameter"] for issue in self.inspect(text)], ["10GB"])
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([text], project_facts=FACTS)], ["10"])
                self.assertEqual(self.inspect(text, facts=text), [])
                self.assertTrue(self.inspect("备份固定每日增量。", facts=field + "。"))
                self.assertTrue(self.inspect(field + "且固定每日全量。"))
                self.assertTrue(self.inspect(field + "，响应时间为90毫秒。"))
        self.assertTrue(self.inspect("固定每日全量同步。"))
        self.assertTrue(self.inspect("每日执行增量备份。"))

    def test_increment_row_count_field_does_not_establish_a_schedule_or_value(self):
        field = "每日增量行数"
        text = ("因此，在未获得实际数据特征前，不应指定具体的分区策略或压缩算法，"
                "而是列出需要采集的数据样本字段，包括平均记录大小、每日增量行数、热点数据比例等，"
                "以便后续进行容量规划和性能调优。")
        self.assertEqual(self.inspect(text), [])
        self.assertEqual(self.inspect("包括平均记录大小、每日增量行数、热点数据比例等。"), [])
        self.assertTrue(self.inspect("备份固定每日增量。", facts=field + "。"))
        self.assertTrue(self.inspect(field + "且固定每日全量。"))
        for value, number in (("8GB", "8"), ("10000条", "10000")):
            statement = field + "为" + value + "。"
            with self.subTest(value=value):
                self.assertEqual([issue["parameter"] for issue in self.inspect(statement)], [value])
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([statement], project_facts=FACTS)], [number])
                self.assertEqual(self.inspect(statement, facts=statement), [])
        later = "收集每日增量行数字段，响应时间为90毫秒。"
        self.assertEqual([issue["parameter"] for issue in self.inspect(later)], ["90毫秒"])
        self.assertEqual([issue["parameter"] for issue in
                          unsupported_numeric_claims([later], project_facts=FACTS)], ["90"])

    def test_explicit_terminology_definitions_qualify_only_their_quoted_labels(self):
        text = ("为避免后期返工，建议在技术方案文档中建立术语对照表，"
                "统一“数据孤岛”、“质量失控”、“权限边界”等概念在本项目中的具体指代。")
        self.assertEqual(self.inspect(text), [])
        for left, right in (("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'")):
            definition = f"统一{left}数据孤岛{right}在本项目中的术语定义"
            with self.subTest(quote=left):
                self.assertEqual(self.inspect(definition + "。"), [])
                later = definition + "，但现有系统存在数据孤岛。"
                self.assertEqual([issue["code"] for issue in self.inspect(later)],
                                 ["unsupported_project_status"])
                self.assertEqual([issue["code"] for issue in
                                  self.inspect(f"本项目已经存在{left}数据孤岛{right}。")],
                                 ["unsupported_project_status"])
        self.assertTrue(self.inspect("本项目已统一“数据孤岛”问题。"))
        self.assertEqual([issue.get("parameter") for issue in
                          self.inspect(text + "响应时间为90毫秒。")], ["90毫秒"])
        # Definition grammar does not waive an actual numeric parameter.
        self.assertEqual([issue.get("parameter") for issue in
                          self.inspect("定义“响应时间为90毫秒”这一表述在本项目中的具体指代。")],
                         ["90毫秒"])

    def test_terminology_sources_cannot_authorise_their_quoted_diagnosis_or_values(self):
        status = "现有系统存在数据孤岛。"
        definition = "定义“现有系统存在数据孤岛”这一表述在本项目中的具体指代。"
        self.assertEqual([issue["code"] for issue in self.inspect(status, facts=definition)],
                         ["unsupported_project_status"])
        self.assertEqual(self.inspect(status, facts=status), [])
        self.assertEqual(self.inspect(status, facts=definition + status), [])
        quoted_fact = "本项目已经存在“数据孤岛”。"
        self.assertEqual(self.inspect(quoted_fact, facts=quoted_fact), [])
        numeric = "响应时间为90毫秒。"
        numeric_definition = "定义“响应时间为90毫秒”这一表述在本项目中的具体指代。"
        self.assertTrue(self.inspect(numeric, facts=numeric_definition))
        self.assertTrue(unsupported_numeric_claims([numeric], project_facts=numeric_definition))
        self.assertEqual(self.inspect(numeric, facts=numeric_definition + numeric), [])
        self.assertEqual(unsupported_numeric_claims([numeric], project_facts=numeric_definition + numeric), [])

    def test_assumed_capability_does_not_identify_or_ground_an_unknown_counted_machine(self):
        facts = "项目涉及三套内部业务系统，现有两台数据服务器。"
        template = "因此，不能默认{}能同时承载数据采集的高并发写入与质量监控的大规模扫描任务。"
        self.assertEqual(self.inspect(template.format("这两台数据服务器"), facts=facts), [])
        for noun in ("这两台机器", "这三台数据服务器", "这两台认证服务器",
                     "财务系统的两台数据服务器", "新增的两台数据服务器", "本项目全部两台设备"):
            with self.subTest(noun=noun):
                self.assertEqual([issue["code"] for issue in self.inspect(template.format(noun), facts=facts)],
                                 ["unsupported_parameter"])
        self.assertEqual(self.inspect(template.format("现有两台机器"), facts="现有两台机器。"), [])
        self.assertEqual([issue["code"] for issue in self.inspect("这两台数据服务器确保高可用。", facts=facts)],
                         ["unsupported_capability_claim"])

    def test_demonstrative_artificial_word_does_not_hide_person_counts(self):
        for text in ("针对“支持权限控制和审计”这一人工确认的条件。",
                     "记录这一人工审核步骤。", "核对这一人工处理的记录。"):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
        for text in ("一人完成核查。", "2人负责运维。", "这一人工作于平台运维岗位。",
                     "这一人工确认的条件且2人负责运维。", "这一人工处理步骤的响应时间为90毫秒。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
                if "2" in text or "90" in text:
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
        self.assertTrue(self.inspect("一人完成核查。", facts="这一人工确认的条件。"))
        self.assertEqual(self.inspect("一人完成核查。", facts="一人完成核查。"), [])

    def test_lexical_unique_and_arbitrary_nouns_are_not_quantities(self):
        for text in ("建立唯一人员标识。", "核对任一人员的权限。", "维护唯一台账。"):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
        for text, parameter in (("补充一人运维。", "一人"),
                                ("运维人员配额为两人。", "两人"),
                                ("运维人员配额为2人。", "2人"),
                                ("新增一台交换机。", "一台"),
                                ("新增两台交换机。", "两台"),
                                ("由同一个人复核所有记录。", "一个人")):
            with self.subTest(text=text):
                self.assertEqual([issue["parameter"] for issue in self.inspect(text)], [parameter])
        self.assertEqual([issue["parameter"] for issue in
                          unsupported_numeric_claims(["运维人员配额为2人。"], project_facts=FACTS)], ["2"])

    def test_lexical_noun_exclusion_leaves_later_real_quantities_checked(self):
        for text, parameter, numeric in (
                ("建立唯一人员标识。安排2人运维。", "2人", ["2"]),
                ("维护唯一台账且新增一台交换机。", "一台", []),
                ("核对任一人员的权限。新增两台交换机。", "两台", []),
                ("不得擅自设置唯一人员标识但安排1人运维。", "1人", ["1"]),
                ("不能擅自设定唯一台账，新增一台交换机。", "一台", [])):
            with self.subTest(text=text):
                self.assertEqual([issue["parameter"] for issue in self.inspect(text)], [parameter])
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([text], project_facts=FACTS)], numeric)

    def test_lexical_nouns_cannot_supply_person_or_device_quantity_evidence(self):
        for source, text, numeric in (
                ("建立唯一人员标识。", "补充一人运维。", []),
                ("核对任一人员的权限。", "安排1人运维。", ["1"]),
                ("维护唯一台账。", "新增一台交换机。", []),
                ("维护唯一台账。", "新增1台交换机。", ["1"]),
                ("不得擅自设置唯一人员标识。", "安排1人运维。", ["1"])):
            with self.subTest(source=source, text=text):
                self.assertTrue(self.inspect(text, facts=source))
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([text], project_facts=source)], numeric)
        for source, text in (("补充一人运维。", "补充1人运维。"),
                             ("新增一台交换机。", "新增1台交换机。"),
                             ("建立唯一人员标识。补充一人运维。", "补充1人运维。")):
            with self.subTest(source=source, text=text):
                self.assertEqual(self.inspect(text, facts=source), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=source), [])

    def test_inability_to_infer_is_local_and_does_not_supply_positive_evidence(self):
        for text in ("因此无法直接推断现有的技术债务或性能瓶颈。",
                     "无法推断现有系统已保证高可用。", "无法据此证明本项目已满足可靠性要求。"):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
                for separator in ("但", "且", "，"):
                    self.assertTrue(self.inspect(text[:-1] + separator + "现有系统已保证高可用。"))
                self.assertTrue(self.inspect("现有系统已保证高可用。", facts=text))
                combined = text[:-1] + "且响应时间为90毫秒。"
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([combined], project_facts=FACTS)], ["90"])
        self.assertEqual(self.inspect("现有系统已保证高可用。", facts="现有系统已保证高可用。"), [])
        self.assertTrue(self.inspect("已有事实表明仅有两台设备。"))
        self.assertTrue(self.inspect("现有业务系统需要整合，其必要性体现在确保合成数据平台的可用性与可信度上。"))

    def test_denied_derivation_is_epistemic_and_keeps_later_assertions_checked(self):
        self.assertEqual(self.inspect("现有业务系统的接口资料需调查，因此无法直接推导出具体的适配方案或性能指标。"), [])
        for predicate in ("无法直接推导", "无法直接推导出", "不能据此推导出"):
            denied = predicate + "本项目已保证高可用。"
            with self.subTest(predicate=predicate):
                self.assertEqual(self.inspect(denied), [])
                self.assertTrue(self.inspect("本项目已保证高可用。", facts=denied))
                for separator in ("但", "且", "，"):
                    self.assertTrue(self.inspect(denied[:-1] + separator + "现有系统已保证高可用。"))
                combined = denied[:-1] + "且响应时间为90毫秒。"
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([combined], project_facts=FACTS)], ["90"])
                local_source = denied[:-1] + "且现有系统已保证高可用。"
                self.assertEqual(self.inspect("现有系统已保证高可用。", facts=local_source), [])
        self.assertTrue(self.inspect("能够推导出本项目已保证高可用。"))
        self.assertEqual(self.inspect("本项目已保证高可用。", facts="本项目已保证高可用。"), [])
        self.assertTrue(self.inspect("指出当前多系统并行运行导致的数据标准不一、采集链路复杂以及质量监控缺失等问题。"))

    def test_complete_pending_conclusion_qualifies_only_its_named_status(self):
        pending = "任何关于现有系统存在数据孤岛的结论，均须调查确认。"
        self.assertEqual(self.inspect(pending), [])
        self.assertEqual(self.inspect("任何关于现有系统已保证高可用的结论，均须调查确认。"), [])
        for text in ("任何关于现有系统存在数据孤岛的结论。",
                     "任何关于现有系统存在数据孤岛的结论，均已证实。",
                     "现有系统存在数据孤岛，须确认整改期限。",
                     "任何关于现有系统存在数据孤岛的结论，均须确认整改期限。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
        for text in (pending[:-1] + "，响应时间为90毫秒。",
                     "响应时间为90毫秒且" + pending,
                     pending[:-1] + "但现有系统已保证高可用。",
                     pending[:-1] + "且固定每日全量。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
                if "90" in text:
                    self.assertEqual([issue["parameter"] for issue in
                                      unsupported_numeric_claims([text], project_facts=FACTS)], ["90"])
                    self.assertEqual([issue["code"] for issue in self.inspect(text)], ["unsupported_parameter"])
        # A pending status discussion does not give arbitrary scalar proposals
        # their own confirmation: parameters still need their existing checks.
        self.assertTrue(self.inspect("任何关于现有系统响应时间为90毫秒的结论，均须调查确认。"))

    def test_pending_conclusion_source_cannot_authorise_its_status_or_other_values(self):
        for source, body in (
            ("任何关于现有系统存在数据孤岛的结论，均须调查确认。", "现有系统存在数据孤岛。"),
            ("任何关于本项目已保证高可用的结论，均须调查确认。", "本项目已保证高可用。"),
            ("任何关于现有系统响应时间为90毫秒的结论，均须调查确认。", "现有系统响应时间为90毫秒。"),
        ):
            with self.subTest(source=source):
                self.assertTrue(self.inspect(body, facts=source))
                if "90" in body:
                    self.assertEqual([issue["parameter"] for issue in
                                      unsupported_numeric_claims([body], project_facts=source)], ["90"])
        discussion = "任何关于现有系统存在数据孤岛的结论，均须调查确认。"
        for source in ("响应时间为90毫秒且" + discussion,
                       "响应时间为90毫秒，" + discussion):
            with self.subTest(source=source):
                self.assertEqual(self.inspect("响应时间为90毫秒。", facts=source), [])
                self.assertEqual(unsupported_numeric_claims(["响应时间为90毫秒。"], project_facts=source), [])
                self.assertTrue(self.inspect("现有系统存在数据孤岛。", facts=source))

    def test_each_one_quantifier_enumerates_checks_without_authorising_fixed_values(self):
        facts = "项目涉及三套内部业务系统，现有两台数据服务器。"
        for text in ("逐项记录每一条核查结论。", "为每一条告警建立核查记录。",
                     "针对每一套业务系统调查接口文档。", "为每一台服务器建立配置清单。",
                     "核对每一项待确认事项。"):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text, facts=facts), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=facts), [])
        for text in ("项目仅保留一条核查结论。", "项目仅保留1条核查结论。",
                     "每条记录8GB。", "每一条记录8GB。", "每一条记录保留90天。",
                     "逐项记录每一条核查结论，响应时间固定为90毫秒。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=facts))
                if text != "项目仅保留一条核查结论。":
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))
        for text, number in (("每一条记录8GB。", "8"), ("每一条记录保留90天。", "90")):
            self.assertEqual([issue["parameter"] for issue in
                              unsupported_numeric_claims([text], project_facts=facts)], [number])
        self.assertTrue(self.inspect("项目仅保留1条核查结论。", facts="逐项记录每一条核查结论。"))

    def test_each_one_and_elided_allocation_never_inherit_project_totals(self):
        for text in ("每一套业务系统配置两台服务器。", "每一个部门配置2台服务器。",
                     "每一套独立的内部业务系统配置2台服务器。",
                     "每套配置两台服务器。", "每一套配置2台服务器。", "各套部署2台数据服务器。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
                if "2" in text:
                    self.assertEqual([issue["parameter"] for issue in
                                      unsupported_numeric_claims([text], project_facts=FACTS)], ["2"])

    def test_distributive_evidence_stays_local_to_its_explicit_or_elided_object(self):
        for source, text in (("每一套业务系统配置两台服务器。", "每套业务系统配置2台服务器。"),
                             ("每套业务系统配置两台服务器。", "每一套业务系统配置2台服务器。"),
                             ("每一个部门配置两台服务器。", "每个部门配置2台服务器。"),
                             ("每套配置两台服务器。", "每一套配置2台服务器。")):
            with self.subTest(source=source):
                self.assertEqual(self.inspect(text, facts=source), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=source), [])
                self.assertTrue(self.inspect("项目共有2台服务器。", facts=source))
                self.assertTrue(unsupported_numeric_claims(["项目共有2台服务器。"], project_facts=source))
        self.assertTrue(self.inspect("每一套配置2台服务器。", facts="每套业务系统配置两台服务器。"))
        self.assertTrue(self.inspect("财务系统配置2台服务器。", facts="每套配置两台服务器。"))

    def test_requested_count_keeps_named_nouns_and_actual_owner_context(self):
        for noun in ("财务业务系统", "HR业务系统", "源系统A", "星云档案系统"):
            text = "向系统集成商索取3套 " + noun + "的清单。"
            with self.subTest(noun=noun):
                self.assertTrue(self.inspect(text))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
                self.assertEqual(self.inspect(text, facts="现有三套 " + noun + "。"), [])
        for text in ("请运维部门核对财务系统的2台数据服务器清单。",
                     "向系统建设单位索取财务系统配置2台数据服务器的清单。",
                     "向系统集成商索取每套业务系统配置2台数据服务器的清单。",
                     "向每套业务系统索取2台数据服务器。",
                     "请各部门核对2台数据服务器的清单。",
                     "财务系统至少需要2台数据服务器。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
        facts = "财务系统配置两台数据服务器。"
        self.assertEqual(self.inspect("向系统集成商索取财务系统的2台数据服务器清单。", facts=facts), [])
        self.assertTrue(self.inspect("向系统集成商索取人事系统的2台数据服务器清单。", facts=facts))
        self.assertEqual(self.inspect("向每套业务系统索取2台数据服务器。",
                                      facts="每套业务系统配置两台数据服务器。"), [])

    def test_count_owner_groups_and_allocations_survive_noun_anchoring(self):
        facts = "财务系统和人事系统配置两台数据服务器。"
        self.assertEqual(self.inspect("财务系统和人事系统的2台数据服务器清单。", facts=facts), [])
        self.assertTrue(self.inspect("财务系统和风控系统的2台数据服务器清单。", facts=facts))
        for text in ("每套业务系统配置2台数据服务器。", "财务系统配置2台数据服务器。"):
            self.assertTrue(self.inspect(text))
        collective = "所有业务系统共用两台数据服务器。"
        self.assertEqual(self.inspect("所有业务系统共用2台数据服务器。", facts=collective), [])
        self.assertTrue(self.inspect("每套业务系统配置2台数据服务器。", facts=collective))

    def test_daily_increment_size_is_a_field_and_does_not_establish_a_schedule(self):
        for text in ("关于数据规模、每日增量大小。", "应收集每日增量大小的统计资料。",
                     "核对每小时增量大小字段。"):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
        for text in ("每日执行增量同步。", "每小时增量备份。", "备份固定每日增量。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
                self.assertTrue(self.inspect(text, facts="每日增量大小。每小时增量大小。"))
        for text in ("每日增量大小为8GB。", "每日增量大小且响应时间为90毫秒。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
                self.assertNotIn("每日", {issue.get("parameter") for issue in self.inspect(text)})
        self.assertEqual(self.inspect("每日增量大小为8GB。", facts="每日增量大小为8GB。"), [])

    def test_uniform_standard_deficit_requires_a_project_status_fact(self):
        real = "本项目的核心必要性在于解决现有三套内部业务系统在数据采集、存储及质量监控环节缺乏统一标准的问题。"
        for body in (real, "现有业务系统缺乏统一标准。", "现有业务系统缺乏统一的标准。",
                     "当前已确认的事实包括：项目拟整合的业务系统数量为3套。" + real):
            with self.subTest(body=body):
                self.assertEqual({issue["code"] for issue in self.inspect(body)}, {"unsupported_project_status"})
                self.assertEqual(unsupported_numeric_claims([body], project_facts=FACTS), [])
        self.assertEqual(self.inspect(real, facts=FACTS["background"] + real), [])
        for body in ("若现有业务系统缺乏统一标准，则核查接口规范。",
                     "调查现有业务系统是否缺乏统一标准。", "现有业务系统缺乏统一标准待确认。",
                     "不能推断现有业务系统缺乏统一标准。", "现有业务系统并非缺乏统一标准。",
                     "并非现有业务系统缺乏统一标准。", "现有业务系统不缺乏统一标准。",
                     "本项目旨在建立统一标准。"):
            with self.subTest(body=body):
                self.assertEqual(self.inspect(body), [])
        for separator in ("但", "且", "，"):
            body = "现有业务系统并非缺乏统一标准" + separator + "现有业务系统缺乏统一标准。"
            with self.subTest(separator=separator):
                self.assertEqual([issue["code"] for issue in self.inspect(body)], ["unsupported_project_status"])
        self.assertEqual([issue["code"] for issue in
                          self.inspect("现有业务系统缺乏统一标准，须确认整改期限。")], ["unsupported_project_status"])
        combined = "现有业务系统并非缺乏统一标准且响应时间为90毫秒。"
        self.assertEqual([issue["parameter"] for issue in self.inspect(combined)], ["90毫秒"])
        self.assertEqual([issue["parameter"] for issue in
                          unsupported_numeric_claims([combined], project_facts=FACTS)], ["90"])

    def test_qualified_standard_deficit_sources_cannot_authorise_the_status(self):
        claim = "现有业务系统缺乏统一标准。"
        for source in ("若现有业务系统缺乏统一标准，则核查接口规范。",
                       "调查现有业务系统是否缺乏统一标准。", "不能推断现有业务系统缺乏统一标准。",
                       "并非现有业务系统缺乏统一标准。", "现有业务系统并非缺乏统一标准。"):
            with self.subTest(source=source):
                self.assertEqual([issue["code"] for issue in self.inspect(claim, facts=source)],
                                 ["unsupported_project_status"])
        self.assertEqual(self.inspect(claim, facts=claim), [])
        source = "现有业务系统并非缺乏统一标准但现有业务系统缺乏统一标准。"
        self.assertEqual(self.inspect(claim, facts=source), [])

    def test_necessity_reference_matches_the_complete_supported_status_proposition(self):
        proposition = "现有三套内部业务系统在数据采集、存储及质量监控环节缺乏统一标准。"
        body = "本项目的核心必要性在于解决" + proposition[:-1] + "的问题。"
        facts = FACTS["background"] + proposition
        self.assertEqual(self.inspect(body, facts=facts), [])
        self.assertEqual(unsupported_numeric_claims([body], project_facts=facts), [])
        for source in ("现有内部业务系统缺乏统一标准。",
                       "现有三套内部业务系统在数据采集环节缺乏统一标准。",
                       proposition.replace("三套", "四套"),
                       proposition.replace("内部业务系统", "财务系统"),
                       "并非" + proposition,
                       "若" + proposition[:-1] + "则核查接口规范。",
                       proposition.replace("缺乏", "是否缺乏")):
            with self.subTest(source=source):
                self.assertEqual([issue["code"] for issue in
                                  self.inspect(body, facts=FACTS["background"] + source)],
                                 ["unsupported_project_status"])
        named_source = FACTS["background"] + proposition.replace("内部业务系统", "财务系统")
        self.assertEqual(self.inspect(body.replace("内部业务系统", "财务系统"), facts=named_source), [])
        self.assertEqual([issue["code"] for issue in
                          self.inspect(body + "现有系统缺乏统一认证。", facts=facts)], ["unsupported_project_status"])
        self.assertEqual([issue["parameter"] for issue in
                          self.inspect(body + "响应时间为90毫秒。", facts=facts)], ["90毫秒"])
        self.assertEqual([issue["parameter"] for issue in
                          unsupported_numeric_claims([body + "响应时间为90毫秒。"], project_facts=facts)], ["90"])

    def test_negated_inference_qualifies_only_the_local_status_proposition(self):
        for prefix in ("拟统一这一建设意图并不反推", "建设目标不能推断", "设计意图不应推出"):
            text = prefix + "现有系统必然存在数据孤岛或接口格式显著差异。"
            with self.subTest(prefix=prefix):
                self.assertEqual(self.inspect(text), [])
                self.assertTrue(self.inspect("现有系统必然存在数据孤岛。", facts=text))
                for separator in ("但", "且", "，"):
                    joined = text[:-1] + separator + "现有系统缺乏统一认证。"
                    self.assertIn("unsupported_project_status", {issue["code"] for issue in self.inspect(joined)})
                joined = text[:-1] + "且响应时间固定为90毫秒。"
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([joined], project_facts=FACTS)], ["90"])
        self.assertTrue(self.inspect("现有系统存在数据孤岛。"))
        self.assertEqual(self.inspect("现有系统存在数据孤岛。", facts="现有系统存在数据孤岛。"), [])
        self.assertEqual(self.inspect("建设意图不能反推本项目已保证高可用。"), [])
        self.assertTrue(self.inspect("建设意图不能反推本项目已保证高可用但本项目已保证高可用。"))

    def test_wont_assign_values_does_not_authorise_positive_source_values(self):
        for modifier in ("", "随意", "擅自"):
            source = "不会" + modifier + "设定每小时增量或每日全量的运行周期。"
            with self.subTest(modifier=modifier):
                self.assertEqual(self.inspect(source), [])
                self.assertTrue(self.inspect("备份固定每日全量。", facts=source))
                for separator in ("，", "且", "但"):
                    combined = source[:-1] + separator + "响应时间固定为90毫秒。"
                    self.assertEqual([issue["parameter"] for issue in
                                      unsupported_numeric_claims([combined], project_facts=FACTS)], ["90"])
        self.assertEqual(self.inspect("备份固定每日全量。", facts="备份固定每日全量。"), [])

    def test_sequence_actions_do_not_inherit_prior_prohibition_or_question(self):
        for boundary in ("随后", "然后", "接着", "继而"):
            for prefix in ("不能擅自设定每小时增量", "请确认是否允许备份"):
                text = prefix + boundary + "固定每日全量。"
                with self.subTest(boundary=boundary, prefix=prefix):
                    self.assertIn("每日", {issue.get("parameter") for issue in self.inspect(text)})
                    actual = prefix + boundary + "响应时间固定为90毫秒。"
                    self.assertEqual([issue["parameter"] for issue in
                                      unsupported_numeric_claims([actual], project_facts=FACTS)], ["90"])
                    self.assertTrue(self.inspect("备份固定每小时增量。", facts=text))
                    self.assertEqual(self.inspect("备份固定每日全量。", facts=text), [])

    def test_later_verification_does_not_qualify_an_earlier_fixed_value(self):
        for verification in ("确认是否", "核实是否", "验证能否", "检查是否"):
            for prefix in ("固定每日全量", "响应时间固定为90毫秒"):
                text = prefix + "后" + verification + "满足恢复要求。"
                with self.subTest(prefix=prefix, verification=verification):
                    self.assertTrue(self.inspect(text))
                    if "90" in prefix:
                        self.assertEqual([issue["parameter"] for issue in
                                          unsupported_numeric_claims([text], project_facts=FACTS)], ["90"])
        for text in ("备份后的一天窗口待确认。", "备份后30天的数据保留窗口待确认。",
                     "每日全量仅为候选，该周期待确认。", "若业务确认则可选每日全量且该周期待确认。"):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])

    def test_per_object_server_evidence_supports_members_but_not_project_totals(self):
        for scope, member, other in (("每套业务系统", "财务系统", "财务部门"),
                                     ("每系统", "财务系统", "财务部门"),
                                     ("每个部门", "财务部门", "财务系统"),
                                     ("每个数据库", "财务数据库", "财务系统")):
            facts = f"{scope}配置两台服务器。"
            with self.subTest(scope=scope):
                for text in (f"{scope}配置2台服务器。", f"{member}配置2台服务器。"):
                    self.assertEqual(self.inspect(text, facts=facts), [])
                    self.assertEqual(unsupported_numeric_claims([text], project_facts=facts), [])
                for text in ("本项目共有2台服务器。", "所有业务系统共有2台服务器。",
                             f"{other}配置2台服务器。", f"{member}配置3台服务器。"):
                    self.assertTrue(self.inspect(text, facts=facts))
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))
        mixed = "三套业务系统中每套业务系统配置两台服务器。"
        self.assertEqual(self.inspect("三套业务系统的数据采集。", facts=mixed), [])
        self.assertTrue(self.inspect("本项目共有2台服务器。", facts=mixed))

    def test_collective_server_count_does_not_become_each_object_or_named_exclusive_count(self):
        for group, member in (("所有业务系统", "财务系统"), ("全部部门", "财务部门"),
                              ("所有数据库", "财务数据库")):
            facts = f"{group}共用两台服务器。"
            with self.subTest(group=group):
                self.assertEqual(self.inspect("本项目共有2台服务器。", f"{group}共用2台服务器。", facts=facts), [])
                for text in (f"{member}配置2台服务器。", f"每个{group[2:]}配置2台服务器。"):
                    self.assertTrue(self.inspect(text, facts=facts))
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))
        self.assertTrue(self.inspect("人事系统配置2台服务器。", facts="财务系统配置两台服务器。"))

    def test_recovery_time_and_recovery_point_are_distinct_objectives(self):
        for text in ("后续确认恢复时间目标（RTO/RPO）。", "RTO、RPO均为恢复时间目标。"):
            with self.subTest(text=text):
                self.assertIn("technical_concept_mismatch", {issue["code"] for issue in self.inspect(text)})
        self.assertEqual(self.inspect("恢复时间目标（RTO）与恢复点目标（RPO）均待业务确认。",
                                      "将恢复时间目标（RTO/RPO）合称是错误表述。"), [])

    def test_partition_causality_guard_is_narrow_and_requires_a_clear_claim(self):
        incorrect = (
            "若误选低基数字段作为分区依据，可能导致大量小文件产生。",
            "若误选低基数字段作为分区依据，可能导致大量小文件产生，但该结论待核实。",
            "低基数分区键可能导致大量小文件，进而增加元数据管理开销，但这并非绝对规律，需通过EXPLAIN ANALYZE验证执行计划。",
        )
        for text in incorrect:
            with self.subTest(text=text):
                self.assertIn("technical_concept_mismatch", {issue["code"] for issue in self.inspect(text)})
        self.assertEqual(self.inspect(
            "低基数本身并不必然导致大量小文件；应结合分区方式、键基数和分布、数据量及负载核验。",
            "低基数是否会造成小文件，需先核对分区方式、数据分布和写入负载。",
            "按值分区时，高基数键在特定数据分布与负载下可能形成较多分区，需结合实测核验。",
            "低基数字段可能造成数据集中或分布不均，而按大量不同键值逐一建分区或使用过细的分区粒度可能形成过多小分区，增加规划、元数据及维护开销，具体影响需负载测试验证。"), [])
        self.assertIn("technical_concept_mismatch", {issue["code"] for issue in self.inspect(
            "低基数本身并不导致大量小文件，但低基数列作为分区依据会形成过多小分区。")})

    def test_postgresql_readonly_tablespace_claim_requires_postgresql_scope(self):
        self.assertIn("technical_concept_mismatch", {issue["code"] for issue in
            self.inspect("PostgreSQL建议将审计记录归档至专用只读表空间。")})
        self.assertIn("technical_concept_mismatch", {issue["code"] for issue in
            self.inspect("建议将审计记录归档至专用只读表空间，相关配置待确认。",
                         references="PostgreSQL 18官方文档作为通用参考。")})
        self.assertEqual(self.inspect("Oracle支持将审计记录归档至专用只读表空间。",
                                       references="PostgreSQL 18官方文档作为通用参考。"), [])
        self.assertEqual(self.inspect("PostgreSQL不提供原生只读表空间配置；表空间存储隔离、SQL写入权限、只读事务和归档防篡改应分别处理。",
                                      "Oracle支持将表空间设置为只读。",
                                      references="PostgreSQL 18官方文档作为通用参考。"), [])

    def test_kafka_connect_exactly_once_guard_preserves_supported_scope_boundaries(self):
        incorrect = "根据Apache Kafka官方文档关于Connect组件的论述，端到端的“恰好一次”语义并非框架自带功能。"
        self.assertIn("technical_concept_mismatch", {issue["code"] for issue in self.inspect(incorrect)})
        self.assertEqual(self.inspect(
            "Kafka Connect支持恰好一次处理路径，具体connector、模式与配置须核验，端到端边界需验证。",
            "Kafka Connect具备恰好一次能力，但不自动保证端到端恰好一次，仍需核验connector与配置。",
            "Kafka Connect不能仅凭框架名称保证端到端恰好一次语义，须核验connector、模式及配置。",
            "将Kafka Connect恰好一次语义说成并非框架自带功能是错误表述。"), [])

    def test_alertmanager_inhibition_is_distinct_from_grouping_and_repeat_controls(self):
        incorrect = "Alertmanager配置抑制规则，当同一数据源出现连续相同错误时，仅发送一次聚合通知。"
        self.assertIn("technical_concept_mismatch", {issue["code"] for issue in self.inspect(incorrect)})
        self.assertIn("technical_concept_mismatch", {issue["code"] for issue in self.inspect(
            "Alertmanager将抑制规则用于相同告警的聚合去重。")})
        self.assertEqual(self.inspect(
            "Alertmanager用inhibition抑制与主告警匹配的相关告警，group_by将同一告警组本次通知合并成一次，repeat_interval控制后续提醒。",
            "Alertmanager的inhibition不是分组聚合或去重；相关告警抑制、group_by和repeat_interval分别配置。",
            "Alertmanager抑制因主告警触发的相关服务告警，不代表持续告警只通知一次。"), [])

    def test_alertmanager_feature_list_and_actual_reviewed_distinction_are_valid(self):
        self.assertEqual(self.inspect(
            "参考Prometheus官方文档关于告警概览的论述，Alertmanager负责静默、抑制及聚合功能，"
            "其中inhibition机制用于抑制符合条件的相关告警，这与告警分组聚合及repeat_interval控制的"
            "重复提醒属于不同维度的配置策略",
            "Alertmanager负责静默、抑制及聚合功能，其中inhibition机制用于抑制符合条件的相关告警。",
            "Alertmanager的告警抑制、分组聚合和重复通知分别由inhibition、group_by及repeat_interval控制。",
            "Alertmanager通过inhibition抑制相关告警并通过group_by分组聚合。",
            "Alertmanager的inhibition用于抑制相关告警而group_by负责分组聚合。",
            "Alertmanager的inhibition不代表相同告警只通知一次。",
            "Alertmanager不能将inhibition用于相同告警的聚合去重。"), [])

    def test_alertmanager_correct_clause_never_excuses_a_separate_real_error(self):
        for text in (
            "Alertmanager的inhibition不是分组聚合，但inhibition用于相同告警的聚合去重。",
            "Alertmanager的inhibition负责分组聚合，repeat_interval不同于静默。",
            "Alertmanager的inhibition不是分组聚合，当同一数据源出现连续相同错误时，仅发送一次聚合通知。",
            "Alertmanager通过inhibition聚合去重，group_by与repeat_interval属于不同维度。",
            "Alertmanager的inhibition不是分组聚合，却通过inhibition执行相同告警去重。",
            "Alertmanager的inhibition不是分组聚合且inhibition负责相同告警去重。",
            "Alertmanager由inhibition进行相同告警的分组聚合。",
            "Alertmanager的inhibition可将相同告警聚合为一条。",
            "Alertmanager的抑制规则会对相同告警进行分组。",
            "Alertmanager的inhibition让相同告警去重。",
        ):
            with self.subTest(text=text):
                self.assertIn("technical_concept_mismatch", {issue["code"] for issue in self.inspect(text)})

    def test_grounded_server_quantity_with_combined_modifiers(self):
        self.assertEqual(self.inspect("连接三套内部业务系统及两台现有数据服务器。",
                                      "针对两台现有数据服务器开展资源评估。"), [])

    def test_paired_quotes_bind_counts_only_to_adjacent_generic_objects(self):
        for number, chinese in (("2", "两"), ("5", "五"), ("9", "九")):
            facts = f"现有数据服务器数量为{chinese}台。业务系统数量为{chinese}套。"
            for left, right in (("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'")):
                for text in (
                    f"资料仅提及{left}数据服务器{right}数量为{number}台。",
                    f"清单中的{left}数据服务器{right}数量为{left}{chinese}台{right}。",
                    f"沿用{number}台{left}数据服务器{right}。",
                    f"沿用{left}{number}台{right}数据服务器。",
                    f"{left}内部业务系统{right}数量为{number}套。",
                    f"接入{number}套{left}内部业务系统{right}。",
                ):
                    with self.subTest(text=text, facts=facts):
                        self.assertEqual(self.inspect(text, facts=facts), [])
                        self.assertEqual(unsupported_numeric_claims([text], project_facts=facts), [])

    def test_quoted_quantities_preserve_names_allocations_and_unsupported_values(self):
        for text in (
            "资料提及“数据服务器”数量为4台。",
            "资料提及“风控服务器”数量为2台。",
            "资料提及“星云档案系统”数量为3套。",
            "财务系统的“数据服务器”数量为2台。",
            "每套业务系统的“数据服务器”数量为2台。",
            "服务器数量的任意表述（如“2台”）均视为无效推断。",
        ):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
        facts = "财务系统配置两台数据服务器。"
        self.assertEqual(self.inspect("财务系统的“数据服务器”数量为2台。", facts=facts), [])
        self.assertTrue(self.inspect("人事系统的“数据服务器”数量为2台。", facts=facts))
        self.assertTrue(self.inspect("“数据服务器”数量为2台。", facts=facts))
        self.assertTrue(self.inspect("任何关于服务器数量的固定表述（如“两台”）均视为无效推断。"))
        for name in ("财务业务系统", "HR业务系统", "源系统A", "星云档案系统"):
            text = f"“{name}”数量为三套。"
            facts = f"现有3套 {name}。"
            with self.subTest(name=name):
                self.assertTrue(self.inspect(text))
                self.assertEqual(self.inspect(text, facts=facts), [])
                self.assertTrue(self.inspect("“内部业务系统”数量为3套。", facts=facts))
                self.assertTrue(self.inspect(text, facts="没有" + text))

    def test_quoted_negative_inventory_or_invalidated_sources_cannot_authorize_counts(self):
        for facts in (
            "没有“数据服务器”数量为2台。",
            "不存在“数据服务器”数量为两台。",
            "项目没有“2台”数据服务器。",
            "“数据服务器”数量不为2台。",
            "“数据服务器”数量为2台是无依据的推断。",
        ):
            text = "现有数据服务器数量为2台。"
            with self.subTest(facts=facts):
                self.assertTrue(self.inspect(text, facts=facts))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))
        for join in ("，", "且", "但"):
            facts = "没有“数据服务器”数量为2台" + join + "业务系统数量为3套。"
            with self.subTest(join=join):
                self.assertEqual(self.inspect("现有3套业务系统。", facts=facts), [])
                self.assertEqual(unsupported_numeric_claims(["现有3套业务系统。"], project_facts=facts), [])

    def test_verified_reference_identifiers_do_not_authorize_numeric_project_parameters(self):
        references = "NIST SP 800-207；PostgreSQL 18；Apache Kafka 3.5；ISO/IEC 27001:2022"
        valid = "参考NIST SP 800-207与ISO/IEC 27001:2022；PostgreSQL文档（版本18）及Apache Kafka 3.5只作通用参考。"
        self.assertEqual(unsupported_numeric_claims([valid], project_facts=FACTS, source_context=references), [])
        findings = unsupported_numeric_claims([valid + "日志保留207天，项目端口设置为9080。"],
                                              project_facts=FACTS, source_context=references)
        self.assertEqual([issue["parameter"] for issue in findings], ["207", "9080"])

    def test_absent_or_different_source_version_does_not_pass_numeric_identifier_check(self):
        text = "参考PostgreSQL 19文档及NIST SP 800-207。"
        findings = unsupported_numeric_claims([text], project_facts=FACTS, source_context="PostgreSQL 18")
        self.assertEqual([issue["parameter"] for issue in findings], ["19", "800", "207"])

    def test_numeric_floor_accepts_locally_pending_or_conditional_parameters(self):
        for text in ("备份周期30天仅为候选且待确认。", "若业务确认允许丢失1小时的数据，则据此核验恢复方案。",
                     "端口9080仅为候选且需另行确认。"):
            with self.subTest(text=text):
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
                self.assertEqual(self.inspect(text), [])

    def test_numeric_floor_normalizes_chinese_parameter_evidence(self):
        text = "数据保留期为90天。采集周期为30秒。"
        facts = "数据保留期为九十天。采集周期为三十秒。"
        self.assertEqual(unsupported_numeric_claims([text], project_facts=facts), [])
        self.assertEqual(self.inspect(text, facts=facts), [])

    def test_existing_number_cannot_ground_an_unrelated_unitless_parameter(self):
        facts = "现有数据服务器数量：2台。"
        for text in ("本项目并发连接数为2。", "本项目并发连接数为二。", "本项目指标为2。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=facts))
                if "2" in text:
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))
        self.assertEqual(unsupported_numeric_claims(["项目工资3000。"], project_facts="项目工资3000。"), [])
        extra = unsupported_numeric_claims(["项目工资3000以及绩效2。"], project_facts="项目工资3000。")
        self.assertTrue(any(issue["parameter"] == "2" for issue in extra))

    def test_confirmed_unitless_parameters_match_the_named_parameter(self):
        facts = "本项目并发连接数为二。项目指标为80。"
        self.assertEqual(self.inspect("本项目并发连接数为2。", "项目指标为80。", facts=facts), [])
        self.assertEqual(unsupported_numeric_claims(["本项目并发连接数为2。", "项目指标为80。"], project_facts=facts), [])
        self.assertTrue(self.inspect("本项目线程数为二。", facts=facts))
        self.assertTrue(unsupported_numeric_claims(["本项目线程数为2。"], project_facts=facts))
        self.assertTrue(self.inspect("项目指标为80。", facts="项目指标为80%。"))

    def test_unitless_parameter_pending_scope_is_local(self):
        for text in ("本项目并发连接数为二仅为候选且待确认。", "本项目并发连接数为2待确认。",
                     "若本项目并发连接数为2则需验证配置。"):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
        for text in ("所有参数待确认。并发连接数为2。", "所有参数待确认且并发连接数为2。",
                     "线程数待确认，并发连接数为二。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
                if "2" in text:
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))

    def test_named_system_parameters_do_not_transfer_or_become_project_wide(self):
        for facts, text in (
            ("财务系统备份周期为每周。", "人事系统备份周期为每周。"),
            ("财务系统备份周期为7天。", "人事系统备份周期为七天。"),
            ("财务部门数据保留期为九十天。", "人事部门数据保留期为90天。"),
            ("财务系统并发连接数为二。", "人事系统并发连接数为2。"),
            ("财务系统备份周期为每周。", "本项目备份周期为每周。"),
            ("财务系统备份周期为每周。", "所有业务系统备份周期为每周。"),
            ("所有业务系统中的财务系统备份周期为每周。", "人事系统备份周期为每周。"),
        ):
            with self.subTest(facts=facts, text=text):
                self.assertTrue(self.inspect(text, facts=facts))
                self.assertEqual(self.inspect(facts, facts=facts), [])
                if any(character.isdigit() for character in text):
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))

    def test_explicit_all_system_parameter_evidence_retains_its_shared_scope(self):
        facts = "所有业务系统备份周期为每周。所有业务系统数据保留期为90天。"
        self.assertEqual(self.inspect("财务系统备份周期为每周。", "人事系统备份周期为每周。",
                                      "财务系统数据保留期为九十天。", "所有业务系统备份周期为每周。",
                                      facts=facts), [])
        self.assertEqual(unsupported_numeric_claims(["人事系统数据保留期为90天。"], project_facts=facts), [])

    def test_scope_names_preserve_generic_counts_and_explicit_named_groups(self):
        self.assertEqual(self.inspect("三套内部业务系统的数据采集。",
                                      facts="拟统一三套内部业务系统的数据采集。"), [])
        self.assertEqual(self.inspect("财务系统备份周期为每周。", "人事系统备份周期为每周。",
                                      facts="财务系统和人事系统备份周期为每周。"), [])

    def test_generic_business_system_aliases_keep_the_grounded_count(self):
        for alias in ("不同源的业务系统", "不同的业务系统", "源系统"):
            for number in ("三", "3"):
                text = f"需追踪数据从{number}套{alias}采集的过程。"
                with self.subTest(alias=alias, number=number):
                    self.assertEqual(self.inspect(text), [])
                    self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
            with self.subTest(alias=alias, wrong_count=True):
                text = f"需追踪数据从4套{alias}采集的过程。"
                self.assertIn("unsupported_parameter", {issue["code"] for issue in self.inspect(text)})
                self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))

    def test_generic_aliases_do_not_strip_named_systems_or_expand_named_sources(self):
        for text in (
            "针对3套不同源的财务业务系统开展采集。",
            "针对3套不同的星云档案系统开展采集。",
            "针对3套财务源系统开展采集。",
            "针对3套源系统A开展采集。",
        ):
            with self.subTest(text=text):
                self.assertIn("unsupported_parameter", {issue["code"] for issue in self.inspect(text)})
                self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
        facts = "现有三套财务业务系统。"
        for alias in ("不同源的业务系统", "不同的业务系统", "源系统"):
            text = f"针对3套{alias}开展采集。"
            with self.subTest(alias=alias, named_source=facts):
                self.assertTrue(self.inspect(text, facts=facts))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))
        self.assertTrue(self.inspect("人事源系统备份周期为每周。", facts="财务源系统备份周期为每周。"))
        self.assertEqual(self.inspect("针对3套源系统A开展采集。", facts="现有三套源系统A。"), [])
        self.assertTrue(self.inspect("针对3套源系统B开展采集。", facts="现有三套源系统A。"))

    def test_real_generic_system_counts_do_not_capture_arbitrary_prose_prefixes(self):
        facts = {"background": "合成测试：项目需要汇聚3套内部业务系统。现有数据服务器数量：2台。",
                 "items": [{"name": "数据服务器", "quantity": 2, "unit": "台"}]}
        for text in (
            "由于缺乏三套业务系统的详细技术规格书和数据字典",
            "结合三套业务系统的数据增量趋势",
            "确认存在三套内部业务系统（具体数量以现场最终盘点为准）",
            "模拟从三套业务系统抽取全量历史数据",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text, facts=facts), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=facts), [])
        self.assertTrue(self.inspect("结合三套星云档案系统的数据增量趋势", facts=facts))
        named = "现有三套星云档案系统。"
        self.assertEqual(self.inspect("结合三套星云档案系统的数据增量趋势", facts=named), [])
        self.assertTrue(self.inspect("结合三套远航档案系统的数据增量趋势", facts=named))

    def test_finite_generic_system_modifiers_keep_only_the_grounded_count(self):
        for modifier in ("独立", "独立的", "彼此独立的", "相互独立的"):
            for noun in ("业务系统", "内部业务系统"):
                for number in ("三", "3"):
                    text = f"项目涉及{number}套{modifier}{noun}。"
                    with self.subTest(modifier=modifier, noun=noun, number=number):
                        self.assertEqual(self.inspect(text), [])
                        self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
                text = f"需汇聚4套{modifier}{noun}的数据。"
                with self.subTest(modifier=modifier, noun=noun, wrong_count=True):
                    self.assertTrue(self.inspect(text))
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))

    def test_generic_modifiers_never_strip_named_systems_or_deployment_status(self):
        for noun in ("财务业务系统", "HR业务系统", "源系统A", "源系统B", "星云档案系统",
                     "高可用的内部业务系统", "已验收的内部业务系统"):
            text = f"项目涉及3套独立的{noun}。"
            with self.subTest(noun=noun):
                self.assertTrue(self.inspect(text))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
        for noun in ("财务业务系统", "HR业务系统", "源系统A"):
            facts = f"现有三套独立的{noun}。"
            with self.subTest(named_source=noun):
                self.assertEqual(self.inspect(f"接入3套独立的{noun}。", facts=facts), [])
                self.assertTrue(self.inspect("接入3套独立的内部业务系统。", facts=facts))
        self.assertIn("unsupported_project_status", {issue["code"] for issue in self.inspect(
            "目前这三套独立的内部业务系统处于独立运行状态。")})
        self.assertTrue(self.inspect("人事系统配置2台服务器。", facts="财务系统配置两台服务器。"))
        self.assertTrue(self.inspect("每套独立的内部业务系统配置2台服务器。"))

    def test_generic_modifiers_preserve_each_object_and_collective_allocations(self):
        for modifier in ("独立", "独立的", "彼此独立的", "相互独立的"):
            group = modifier + "内部业务系统"
            per_object = f"每套{group}配置两台服务器。"
            collective = f"所有{group}共用两台服务器。"
            with self.subTest(group=group):
                for text in (f"每套{group}配置2台服务器。", "财务系统配置2台服务器。"):
                    self.assertEqual(self.inspect(text, facts=per_object), [])
                    self.assertEqual(unsupported_numeric_claims([text], project_facts=per_object), [])
                    self.assertTrue(self.inspect(text, facts=collective))
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=collective))
                self.assertTrue(self.inspect("本项目共有2台服务器。", facts=per_object))
                self.assertEqual(self.inspect("本项目共有2台服务器。", facts=collective), [])
                self.assertTrue(self.inspect(f"每套{group}配置2台服务器。"))
                shared_parameter = f"所有{group}备份周期为每日。"
                self.assertEqual(self.inspect("人事系统备份周期为每日。", facts=shared_parameter), [])
                self.assertTrue(self.inspect(shared_parameter, facts="财务系统备份周期为每日。"))

    def test_fixed_protocol_and_percentile_names_only_exempt_their_lexical_digits(self):
        for text in (
            "由于未提供现有的身份认证体系细节（如是否采用LDAP、OAuth2或自建账号系统），集成方式需作为待确认项处理",
            "由于未提供现有的身份认证体系细节（如是否采用LDAP、OAuth2.0或自建账号系统），集成方式需作为待确认项处理",
            "压力测试报告中的P99延迟低于业务容忍阈值",
            "复核OAuth2、oauth2.0与p99指标。",
        ):
            with self.subTest(text=text):
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
        for text, value in (
            ("使用OAuth2，固定端口为2。", "2"),
            ("使用OAuth2.0，固定周期为2.0天。", "2.0"),
            ("P99延迟固定为99毫秒。", "99"),
            ("MyOAuth2Client和P990不能充当经过核验的版本来源。", "990"),
            ("未引用的软件版本21不能借协议名OAuth2放行。", "21"),
        ):
            with self.subTest(text=text):
                self.assertTrue(any(issue["parameter"] == value for issue in
                                    unsupported_numeric_claims([text], project_facts=FACTS)))

    def test_utf8_only_exempts_the_standard_encoding_token(self):
        for text in ("默认采用UTF-8编码假设存在风险，必须现场验证。", "字段编码UTF-8需核实。",
                     "复核utf-8编码与转换异常。"):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
        for text, value in (("采用UTF-8，固定端口为8。", "8"), ("采用UTF-8且保留周期为8天。", "8"),
                            ("编码标记为UTF-80。", "80"), ("转换类名为MyUTF-8Client。", "8")):
            with self.subTest(text=text):
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([text], project_facts=FACTS)], [value])

    def test_prohibited_nominal_performance_promises_keep_local_scope(self):
        prohibition = "严禁在无依据情况下设定秒级或分钟级性能承诺"
        self.assertEqual(self.inspect(prohibition), [])
        self.assertEqual(self.inspect("严禁设定90毫秒的性能承诺。"), [])
        self.assertEqual(unsupported_numeric_claims(["严禁设定90毫秒的性能承诺。"], project_facts=FACTS), [])
        for join in ("。", "，", ",", "但", "但是", "而", "却", "且", "并"):
            text = prohibition + join + "平台响应固定为90毫秒。"
            with self.subTest(join=join):
                self.assertIn("90毫秒", {issue.get("parameter") for issue in self.inspect(text)})
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([text], project_facts=FACTS)], ["90"])
        for text in ("平台设定秒级或分钟级性能承诺。", "严禁修改接口但平台设定秒级性能承诺。",
                     "角色变更十分钟生效。", "审计日志保留六个月。"):
            with self.subTest(text=text):
                self.assertIn("unsupported_parameter", {issue["code"] for issue in self.inspect(text)})
        facts = "严禁设定90毫秒的性能承诺。"
        self.assertTrue(self.inspect("平台承诺90毫秒响应。", facts=facts))
        self.assertTrue(unsupported_numeric_claims(["平台承诺90毫秒响应。"], project_facts=facts))

    def test_prohibited_numeric_promises_do_not_assert_performance(self):
        for prefix in ('不得', '不能', '不应', '无法', '不'):
            text = f'此处{prefix}承诺秒级或分钟级的固定时效'
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
        for text in (
            '此处不得承诺秒级时效。但平台保证分钟级响应。',
            '不能承诺分钟级响应，系统实际每秒采集一次。',
            '不得承诺秒级时效且固定响应为90毫秒。',
        ):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
        self.assertTrue(self.inspect('平台保证分钟级响应。', facts='不得承诺分钟级响应。'))

    def test_prohibited_promises_allow_local_modifiers_and_keep_following_claims(self):
        for text in (
            "不得在无依据情况下承诺秒级或分钟级同步。",
            "不能在缺少实测结果时直接承诺90毫秒的响应。",
            "不应在未经验证的情况下预先承诺秒级时效。",
            "无法在缺少测试结果时合理承诺每秒同步。",
            "此处不预先承诺90毫秒的固定时效。",
            "不得未经验证就承诺90毫秒响应。",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
        for join in ("。", "，", ",", "但", "但是", "而", "且", "并", "并且", "却"):
            text = f"不得在无依据情况下承诺秒级或分钟级同步{join}响应固定为90毫秒。"
            with self.subTest(join=join):
                self.assertIn("90毫秒", {issue.get("parameter") for issue in self.inspect(text)})
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([text], project_facts=FACTS)], ["90"])
        for prefix in ("不得在尚未确认情况下", "不能在未提供实测结果时", "不得据此"):
            text = f"{prefix}承诺秒级同步而响应固定为90毫秒。"
            with self.subTest(prefix=prefix):
                self.assertIn("90毫秒", {issue.get("parameter") for issue in self.inspect(text)})
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([text], project_facts=FACTS)], ["90"])
        for text in ("不得更改接口且承诺90毫秒响应。", "平台承诺90毫秒响应。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
        facts = "不得在无依据情况下承诺90毫秒响应。"
        for text in ("平台承诺90毫秒响应。", "响应为90毫秒。", "90毫秒"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text, facts=facts))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))

    def test_prohibited_parameter_setting_actions_cover_local_syntax(self):
        for prefix in ("不能擅自", "不得", "不应随意", "严禁无依据地", "不可预先",
                       "不得在缺少实测结果时直接", "不能未经确认就"):
            for action in ("设置", "设定", "制定"):
                for objects in ("每日全量或每小时增量的具体运行周期", "每周全量和每日增量备份",
                                "30分钟的备份间隔", "90毫秒响应指标", "六个月保留周期"):
                    text = f"此处{prefix}{action}{objects}。"
                    with self.subTest(prefix=prefix, action=action, objects=objects):
                        self.assertEqual(self.inspect(text), [])
                        self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])

    def test_prohibited_settings_stop_before_independent_parameters(self):
        for action in ("设置", "设定", "制定"):
            for join in ("。", "，", ",", "但", "但是", "而", "且", "并", "并且", "却"):
                text = f"不得在未提供实测结果时擅自{action}每日全量或每小时增量的周期{join}响应固定为90毫秒。"
                with self.subTest(action=action, join=join):
                    self.assertEqual({issue.get("parameter") for issue in self.inspect(text)}, {"90毫秒"})
                    self.assertEqual([issue["parameter"] for issue in
                                      unsupported_numeric_claims([text], project_facts=FACTS)], ["90"])
                text = f"不能擅自{action}每周备份周期{join}每日执行增量备份。"
                with self.subTest(action=action, join=join, cadence=True):
                    self.assertEqual({issue.get("parameter") for issue in self.inspect(text)}, {"每日"})
        text = "不得在未提供实测结果时设定每秒同步而P99延迟固定为90毫秒。"
        self.assertEqual({issue.get("parameter") for issue in self.inspect(text)}, {"90毫秒"})
        self.assertEqual([issue["parameter"] for issue in
                          unsupported_numeric_claims([text], project_facts=FACTS)], ["90"])
        for text in ("平台设定每日全量和每小时增量的具体运行周期。",
                     "严禁修改接口但平台设置每日全量备份。",
                     "不得更改目录并制定每小时增量周期。",
                     "未知指标为8和不得设定每日备份周期。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
        self.assertTrue(unsupported_numeric_claims(
            ["未知指标为8和不得设定每日备份周期。"], project_facts=FACTS))

    def test_prohibited_setting_or_policy_never_becomes_positive_evidence(self):
        for facts, text in (
            ("不能擅自设置每日全量和每小时增量周期。", "备份采用每日全量和每小时增量。"),
            ("不得制定30分钟备份周期。", "备份周期为30分钟。"),
            ("严禁设定90毫秒响应指标。", "响应固定为90毫秒。"),
            ("本项目已规定不得保留30天。", "项目数据保留期为30天。"),
        ):
            with self.subTest(facts=facts):
                self.assertTrue(self.inspect(text, facts=facts))
                if any(character.isdigit() for character in text):
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))

    def test_negative_assignment_or_guarantee_is_not_positive_parameter_evidence(self):
        for prefix in ("不得", "不能", "不应", "严禁", "不可", "不要", "不"):
            for action in ("设为", "固定为"):
                for wording in (f"响应时间{prefix}{action}90毫秒。",
                                f"{prefix}将响应时间{action}九十毫秒。",
                                f"{prefix}直接把响应时间{action}90毫秒。"):
                    text = "响应时间为90毫秒。"
                    with self.subTest(facts=wording):
                        self.assertTrue(self.inspect(text, facts=wording))
                        self.assertTrue(unsupported_numeric_claims([text], project_facts=wording))
            for action in ("保证", "确保"):
                facts = f"平台{prefix}{action}秒级识别。"
                with self.subTest(facts=facts):
                    self.assertTrue(self.inspect("平台实现秒级识别。", facts=facts))
        for facts, text in (
            ("备份周期不能固定为30分钟。", "备份周期为30分钟。"),
            ("响应时间不为90毫秒。", "响应时间为90毫秒。"),
            ("响应时间不是90毫秒。", "响应时间为90毫秒。"),
            ("响应时间并非90毫秒。", "响应时间为90毫秒。"),
            ("响应时间不超过90毫秒。", "响应时间为90毫秒。"),
            ("备份周期不为每周。", "备份周期为每周。"),
        ):
            with self.subTest(facts=facts):
                self.assertTrue(self.inspect(text, facts=facts))
                if any(character.isdigit() for character in text):
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))

    def test_negated_counted_existence_is_not_inventory_evidence(self):
        for denial in ("没有", "不存在", "无", "没有配置", "没有部署", "没有拥有"):
            for number in ("三", "3"):
                for noun in ("业务系统", "内部业务系统", "财务业务系统", "源系统A"):
                    facts = f"项目{denial}{number}套{noun}。"
                    text = f"项目现有3套{noun}。"
                    with self.subTest(facts=facts):
                        self.assertTrue(self.inspect(text, facts=facts))
                        self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))
            for number in ("两", "2"):
                for noun in ("服务器", "主机"):
                    facts = f"项目{denial}{number}台{noun}。"
                    text = f"项目现有2台{noun}。"
                    with self.subTest(facts=facts):
                        self.assertTrue(self.inspect(text, facts=facts))
                        self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))

    def test_positive_assignment_guarantee_and_inventory_evidence_is_retained(self):
        for facts, text in (
            ("响应时间设为90毫秒。", "响应时间为90毫秒。"),
            ("将响应时间设为九十毫秒。", "响应时间为90毫秒。"),
            ("响应时间固定为90毫秒。", "响应时间为90毫秒。"),
            ("备份周期固定为30分钟。", "备份周期为30分钟。"),
            ("平台保证秒级识别。", "平台实现秒级识别。"),
            ("平台确保秒级识别。", "平台实现秒级识别。"),
            ("项目有3套业务系统。", "项目现有3套业务系统。"),
            ("项目存在三套业务系统。", "项目现有3套业务系统。"),
            ("项目配置2台服务器。", "项目现有2台服务器。"),
            ("不为人知的方案响应时间为90毫秒。", "响应时间为90毫秒。"),
            ("没有扩容安排的项目现有2台服务器。", "项目现有2台服务器。"),
        ):
            with self.subTest(facts=facts):
                self.assertEqual(self.inspect(text, facts=facts), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=facts), [])

    def test_negative_evidence_keeps_independent_confirmed_clauses(self):
        for join in ("。", "，", ",", "且", "并", "但", "而"):
            facts = "响应时间不得设为90毫秒" + join + "备份周期固定为30分钟。"
            with self.subTest(join=join, role="response"):
                self.assertTrue(self.inspect("响应时间为90毫秒。", facts=facts))
                self.assertTrue(unsupported_numeric_claims(["响应时间为90毫秒。"], project_facts=facts))
                self.assertEqual(self.inspect("备份周期为30分钟。", facts=facts), [])
                self.assertEqual(unsupported_numeric_claims(["备份周期为30分钟。"], project_facts=facts), [])
            facts = "项目不存在3套业务系统" + join + "现有2台服务器。"
            with self.subTest(join=join, role="inventory"):
                self.assertTrue(self.inspect("项目现有3套业务系统。", facts=facts))
                self.assertTrue(unsupported_numeric_claims(["项目现有3套业务系统。"], project_facts=facts))
                self.assertEqual(self.inspect("项目现有2台服务器。", facts=facts), [])
                self.assertEqual(unsupported_numeric_claims(["项目现有2台服务器。"], project_facts=facts), [])

    def test_prohibited_giving_and_specifying_values_stays_local(self):
        for action in ("给出", "指定"):
            for prefix in ("不得在无依据情况下", "不能直接", "不应擅自", "严禁预先"):
                prohibition = f"{prefix}{action}固定的每日全量或每小时增量同步周期"
                with self.subTest(prohibition=prohibition):
                    self.assertEqual(self.inspect(prohibition), [])
                    self.assertEqual(self.inspect(prohibition + "（具体周期另行确认）。"), [])
                for join in ("。", "，", ",", "但", "而", "且", "并", "并且"):
                    text = prohibition + join + "响应固定为90毫秒。"
                    with self.subTest(action=action, prefix=prefix, join=join):
                        self.assertEqual({issue.get("parameter") for issue in self.inspect(text)}, {"90毫秒"})
                        self.assertEqual([issue["parameter"] for issue in
                                          unsupported_numeric_claims([text], project_facts=FACTS)], ["90"])
                self.assertTrue(self.inspect("每日执行全量同步。", facts=prohibition))
            self.assertTrue(self.inspect(f"平台{action}固定的每日全量或每小时增量同步周期。"))
        self.assertEqual(self.inspect("采集机制不能直接指定固定的同步周期（如每日全量或每小时增量）。"), [])
        self.assertTrue(self.inspect("不得更改目录但平台给出每日全量同步周期。"))

    def test_invalid_metric_hypotheses_qualify_only_the_rejected_lexical_values(self):
        for text in (
            "任何具体的秒级或分钟级恢复指标均视为无效假设。",
            "分钟级的恢复目标应视为缺乏依据的假设。",
            "每日或每小时同步周期都属于无依据的推断。",
            "小时级同步时效是无效的假设。",
            "每周备份周期与每日同步周期均视为无依据承诺。",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])
        invalid = "秒级或分钟级恢复指标均视为无效假设"
        for join in ("。", "，", ",", "但", "而", "且", "并", "并且", "及"):
            text = invalid + join + "响应固定为90毫秒。"
            with self.subTest(join=join):
                self.assertIn("90毫秒", {issue.get("parameter") for issue in self.inspect(text)})
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([text], project_facts=FACTS)], ["90"])
            text = invalid + join + "本项目已保证高可用。"
            with self.subTest(join=join, capability=True):
                self.assertIn("unsupported_capability_claim", {issue["code"] for issue in self.inspect(text)})

    def test_invalid_hypotheses_never_erase_actual_claims_or_support_positive_values(self):
        for text in (
            "平台实际实现秒级恢复指标均视为无效假设。",
            "平台保证每小时同步周期并将其视为无效假设。",
            "平台响应固定为90毫秒是无依据的假设。",
            "角色变更十分钟生效是无依据推断。",
            "审计日志保留六个月是无效假设。",
            "任何服务器数量（如“两台”）均视为无效推断。",
        ):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
        for facts, text in (
            ("秒级恢复指标均视为无效假设。", "平台实现秒级恢复。"),
            ("每日同步周期是无依据推断。", "每日执行同步。"),
            ("响应时间为90毫秒是无依据假设。", "响应时间为90毫秒。"),
        ):
            with self.subTest(facts=facts):
                self.assertTrue(self.inspect(text, facts=facts))
                if any(character.isdigit() for character in text):
                    self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))
        for join in ("，", "且", "但"):
            facts = "秒级恢复指标均视为无效假设" + join + "备份周期固定为30分钟。"
            with self.subTest(join=join):
                self.assertEqual(self.inspect("备份周期为30分钟。", facts=facts), [])
                self.assertEqual(unsupported_numeric_claims(["备份周期为30分钟。"], project_facts=facts), [])

    def test_metric_field_names_requiring_basis_are_locally_qualified(self):
        for text in (
            "备份频率、保留期和秒级等性能指标均须对应具体项目依据。",
            "备份频率、保留期与分钟级响应指标均须有实测依据。",
            "小时级同步指标需要具体项目证据。",
            "检查频率和每日执行周期都必须提供项目依据。",
            "每秒采集频率及秒级识别指标应当具有可信项目依据。",
            "秒级指标和保留期须给出业务依据。",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
                self.assertEqual(unsupported_numeric_claims([text], project_facts=FACTS), [])

    def test_metric_basis_lists_never_qualify_other_values_or_actual_achievements(self):
        listing = "秒级性能指标须有具体项目依据"
        for join in ("。", "，", ",", "但", "而", "且", "并", "并且", "及"):
            text = listing + join + "响应固定为90毫秒。"
            with self.subTest(join=join):
                self.assertIn("90毫秒", {issue.get("parameter") for issue in self.inspect(text)})
                self.assertEqual([issue["parameter"] for issue in
                                  unsupported_numeric_claims([text], project_facts=FACTS)], ["90"])
        for text in ("未知指标为8和秒级性能指标须有项目依据。",
                     "秒级性能指标须有项目依据及未知指标为8。",
                     "90毫秒响应指标须有项目依据。",
                     "30天保留期和秒级性能指标均须有项目依据。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
        for text in ("平台实际实现秒级性能指标须有项目依据。",
                     "平台保证每秒采集频率须有项目依据。",
                     "平台已达到分钟级响应指标须有项目依据。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
        for facts, text in ((listing, "平台实现秒级性能。"),
                            ("每日执行周期须有项目依据。", "每日执行全量备份。")):
            with self.subTest(source_fields=facts):
                self.assertTrue(self.inspect(text, facts=facts))

    def test_frequency_options_to_be_decided_are_locally_pending(self):
        choices = ("需明确告警阈值（如数据完整性低于多少百分比触发报警）、"
                   "检查频率（每日、每小时或实时）以及通知渠道（邮件、短信或即时通讯工具）")
        self.assertEqual(self.inspect(choices), [])
        self.assertEqual(unsupported_numeric_claims([choices], project_facts=FACTS), [])
        self.assertTrue(self.inspect("检查频率为每日。", facts=choices))
        for text in (
            choices + "。检查频率为每日。",
            "需明确职责。检查频率（每日、每小时或实时）。",
            "需明确职责并固定检查频率（每日、每小时或实时）。",
            "需明确检查频率（每日、每小时或实时）但固定每日执行备份。",
        ):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))

    def test_numeric_floor_does_not_apply_one_disclaimer_to_another_claim(self):
        for text in ("所有参数待确认。数据保留90天。", "端口待确认，固定端口9080。",
                     "备份周期30天作为示例。", "建议候选端口9080。"):
            with self.subTest(text=text):
                self.assertTrue(unsupported_numeric_claims([text], project_facts=FACTS))
                self.assertTrue(self.inspect(text))

    def test_conjunction_keeps_fixed_claim_separate_from_other_pending_claim(self):
        for text in ("备份策略采用每日增量且是否需要每周全量待确认。",
                     "接口格式待确认且平台可实现秒级识别。",
                     "接口格式待确认且平台响应时间为0.5秒。"):
            with self.subTest(text=text):
                self.assertTrue(self.inspect(text))
        self.assertEqual(unsupported_numeric_claims(["备份30天仅为候选，该周期待确认。"], project_facts=FACTS), [])

    def test_joined_fixed_cadences_never_inherit_another_claims_pending_status(self):
        for unit in ("工作日", "毫秒", "秒", "分钟", "小时", "天", "日", "周", "星期", "月", "季度", "年"):
            for classifier in ("", "个"):
                cadence = f"每{classifier}{unit}"
                for prefix in ("服务器用途待确认且", "备份周期30天仅为候选且待确认并"):
                    text = prefix + cadence + "执行全量备份。"
                    with self.subTest(unit=unit, classifier=classifier, prefix=prefix):
                        self.assertIn(cadence, {issue.get("parameter") for issue in self.inspect(text)})
                        self.assertEqual(self.inspect(prefix + cadence + "执行全量备份仅为候选且待确认。"), [])
                text = "服务器用途待确认且" + cadence + "执行全量备份并保留90天。"
                with self.subTest(fixed_retention_unit=unit, classifier=classifier):
                    self.assertEqual([issue["parameter"] for issue in
                                      unsupported_numeric_claims([text], project_facts=FACTS)], ["90"])

    def test_same_purpose_parameters_cannot_move_between_different_objects(self):
        cases = (("审计日志保留期为九十天。", "业务数据保留期为90天。"),
                 ("软件预算为十万元。", "硬件预算为10万元。"),
                 ("项目预算为10万元。", "硬件预算为10万元。"),
                 ("审计日志样本采集最近三个月。", "交易数据样本采集最近3个月。"))
        for facts, text in cases:
            with self.subTest(facts=facts):
                self.assertTrue(self.inspect(text, facts=facts))
                self.assertTrue(unsupported_numeric_claims([text], project_facts=facts))
                self.assertEqual(self.inspect(facts, facts=facts), [])

    def test_negative_evidence_does_not_support_opposite_claim(self):
        cases = (("现有系统并非缺乏统一认证。", "现有系统缺乏统一认证。"),
                 ("项目并不采用每周备份。", "项目备份周期为每周。"),
                 ("项目不保留90天的业务数据。", "业务数据保留期为90天。"))
        for facts, text in cases:
            with self.subTest(facts=facts):
                self.assertTrue(self.inspect(text, facts=facts))

    def test_deficit_evidence_does_not_move_between_departments(self):
        facts = "现有财务系统缺乏统一认证。"
        self.assertTrue(self.inspect("现有人事系统缺乏统一认证。", facts=facts))
        self.assertEqual(self.inspect(facts, facts=facts), [])

    def test_numbered_structure_is_not_a_project_parameter(self):
        text = "1. 实时采集\n本文从4个评估维度分析5种校验规则，并逐项测试。\n90天的数据保留周期。"
        issues = unsupported_numeric_claims([text], project_facts={})
        self.assertEqual([issue["parameter"] for issue in issues], ["90"])

    def test_source_version_can_be_attributed_in_natural_language(self):
        text = "Kafka框架自3.3.0版本起提供相关支持。"
        self.assertEqual(unsupported_numeric_claims([text], project_facts={}, source_context="Kafka自3.3.0起支持此特性。"), [])
        self.assertTrue(unsupported_numeric_claims([text], project_facts={}, source_context="Kafka 3.5"))

    def test_grounded_single_server_can_be_assigned_a_temporary_buffer_role(self):
        self.assertEqual(self.inspect("利用现有两台数据服务器中的一台作为临时缓冲节点。"), [])

    def test_same_number_different_subject_or_role_does_not_ground(self):
        self.assertTrue(self.inspect("项目配置两台交换机。"))
        self.assertTrue(self.inspect("业务允许丢失一小时的数据。", facts="恢复目标为一小时。"))
        self.assertTrue(self.inspect("备份采用每周全量。", facts="项目每周召开例会。"))

    def test_grounded_explicit_periods_and_capacities(self):
        facts = "数据保留期为九十天。存储容量为2TB。采集周期为三十秒。"
        self.assertEqual(self.inspect("数据保留期为90天。", "存储容量为二TB。",
                                      "采集周期为30秒。", facts=facts), [])

    def test_missing_facts_and_instructions_are_not_evidence(self):
        facts = {"background": "数据规模未提供。", "requirements": "使用三百GB容量示例。",
                 "conditions": ["每周备份待确认"]}
        self.assertTrue(self.inspect("存储容量三百GB。", facts=facts))
        self.assertTrue(self.inspect("采用每周备份。", facts=facts))

    def test_explicit_pending_and_conditional_candidates(self):
        for text in ("采集最近三个月的数据是否适用需确认。", "至少一周观察期仅为候选且待确认。",
                     "备份策略可选每周全量与每日增量，二者均待确认。",
                     "若业务确认允许丢失一小时的数据，则据此核验恢复方案。",
                     "秒级识别能否实现待实测验证。", "若拓扑仅含两台服务器，则需验证仲裁条件。"):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])

    def test_generic_disclaimer_does_not_hide_fixed_claim_in_same_paragraph(self):
        issues = self.inspect("所有参数均待确认。备份采用每周全量、每日增量。业务允许丢失一小时的数据。")
        self.assertEqual({issue["claim"] for issue in issues},
                         {"备份采用每周全量、每日增量", "业务允许丢失一小时的数据"})
        self.assertTrue(self.inspect("所有参数待确认，但备份采用每周全量。"))
        self.assertTrue(self.inspect("建议每周全量与每日增量作为示例。"))

    def test_pending_one_parameter_does_not_cover_other_fixed_parameter(self):
        issues = self.inspect("保留期待确认，业务允许丢失一小时的数据。")
        self.assertTrue(issues)
        self.assertEqual(issues[0]["claim"], "业务允许丢失一小时的数据")
        self.assertTrue(self.inspect("观察窗口待确认且必须观察至少一周。"))
        self.assertTrue(self.inspect("所有参数均待确认但采用每周全量备份。"))
        self.assertTrue(self.inspect("所有参数均待确认并每日执行增量备份。"))

    def test_distinct_parameters_in_one_clause_have_individual_corrections(self):
        issues = self.inspect("备份采用每周全量和每日增量。")
        self.assertEqual({issue["parameter"] for issue in issues}, {"每周", "每日"})
        self.assertTrue(all(issue["parameter"] in issue["correction"] for issue in issues))

    def test_chapter_ordinals_and_reference_versions_are_not_parameters(self):
        self.assertEqual(self.inspect("第一章 项目背景。第二章 现状分析。",
                                      "参考PostgreSQL 18文档及Kafka 3.5指南。",
                                      "NIST SP 800-207标准与GX Core 1.24.0文档。",
                                      "一、明确边界。二、梳理资料。"), [])

    def test_logical_organization_and_candidate_design_categories_are_allowed(self):
        self.assertEqual(self.inspect("第一阶段调研，第五章设计。两类方案用于比较。",
                                      "本文从三个评估维度分析五种校验规则，并逐项测试。",
                                      "候选方案包括三个阶段，阶段边界待确认。",
                                      "可提供质量日报能力，具体调度周期待确认。"), [])
        self.assertTrue(self.inspect("项目需要三个节点。"))

    def test_chinese_word_boundaries_and_technical_concepts(self):
        self.assertEqual(self.inspect("拟统一三套内部业务系统。", "设计统一元数据管理层。",
                                      "认证与授权是两个独立的控制环节。", "需逐一验证每一个环节。",
                                      "端到端恰好一次语义不能仅靠框架证明。", "应避免一次性定稿。",
                                      "提供一套灵活的验证方法论。", "构建一个可演进的安全框架。",
                                      "必须对每一套业务系统进行端到端测试。",
                                      "可选择每日入库行数波动率作为质量指标。"), [])
        self.assertTrue(self.inspect("固定执行三次重试。"))
        self.assertTrue(self.inspect("预算为一万元。"))

    def test_single_and_double_retry_counts_require_specific_evidence(self):
        for text in ("失败后自动重试一次。", "连接器自动重试两次。", "轮询两次。",
                     "固定重复执行一次。", "执行一次重试。", "需要两次轮询。", "自动重试1次。", "轮询2次。"):
            with self.subTest(text=text):
                self.assertTrue(any(issue["code"] == "unsupported_parameter" for issue in self.inspect(text)))
        self.assertEqual(self.inspect("失败后自动重试一次。", facts="失败后自动重试一次。"), [])
        self.assertEqual(self.inspect("失败后自动重试一次的设置待确认。"), [])
        self.assertEqual(self.inspect("Kafka文档讨论恰好一次语义及失败重试的边界。",
                                      "重试策略需经两次确认。", "轮询配置须经二次复核。",
                                      "每一次采集任务的启动、停止、重试及参数调整均应记录。"), [])
        self.assertTrue(self.inspect("失败后自动重试一次。", facts="采集任务轮询一次。"))

    def test_goal_and_explicit_unknown_performance_do_not_assert_success(self):
        self.assertEqual(self.inspect("本项目的设计目标是确保可靠性。", "本项目需支持高可用。",
                                      "无法量化评估现有三套业务系统的性能瓶颈。",
                                      "不应承诺特定的每秒查询率或数据延迟毫秒数。",
                                      "无法确定具体毫秒级或小时级目标。",
                                      "不得据此宣称项目已满足性能指标。"), [])
        self.assertTrue(self.inspect("本项目的设计目标是确保秒级识别。"))
        self.assertTrue(self.inspect("现有两台服务器已保证可靠性。"))

    def test_assessment_limits_are_not_device_capability_failures(self):
        for text in (
            "两台数据服务器的硬件规格缺失导致容量规划与性能基准测试无法量化。",
            "两台服务器的性能无法评估。",
            "现有两台服务器的性能无法客观评估。",
            "现有两台服务器的高可用方案无法准确地评估。",
            "两台服务器的吞吐能力无法定量评估。",
            "两台服务器的性能无法合理量化。",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.inspect(text), [])
        for verb in ("实现", "达到", "满足", "保证", "维持", "支撑", "提供"):
            text = f"两台服务器无法{verb}高可用。"
            with self.subTest(verb=verb):
                self.assertIn("unsupported_capability_claim", {issue["code"] for issue in self.inspect(text)})

    def test_assessment_limit_does_not_hide_a_later_capability_assertion(self):
        for assessment in ("无法量化", "无法评估", "无法客观评估", "无法量化评估"):
            for join in ("但", "但是", "且", "并", "而", "却", "，", ",", "。"):
                text = f"两台服务器的性能{assessment}{join}本项目已保证高可用。"
                with self.subTest(assessment=assessment, join=join):
                    self.assertIn("unsupported_capability_claim", {issue["code"] for issue in self.inspect(text)})
        for join in ("但", "且", "并", "而", "却", "，", ","):
            text = f"两台服务器的性能无法量化评估{join}已保证高可用。"
            with self.subTest(omitted_subject_join=join):
                self.assertIn("unsupported_capability_claim", {issue["code"] for issue in self.inspect(text)})
        self.assertIn("unsupported_capability_claim", {issue["code"] for issue in
                      self.inspect("两台服务器的性能无法客观评估却无法满足高可用要求。")})

    def test_server_subset_proposal_is_grounded_by_existing_resources(self):
        self.assertEqual(self.inspect("建议将一台服务器配置为主节点。", "另一台服务器作为备用节点。",
                                      "现有两台服务器中的一台作为缓冲节点。", "切换后仅剩一台提供服务。"), [])
        self.assertTrue(self.inspect("建议采购五台服务器。"))
        self.assertTrue(self.inspect("建议新增采购一台服务器。"))
        self.assertTrue(self.inspect("建议新购一台服务器作为备用节点。"))
        self.assertEqual(self.inspect("建议新增采购一台服务器仅为候选且待确认。"), [])
        self.assertTrue(self.inspect("现有服务器数量为一台。"))

    def test_bare_company_document_headers_are_trusted_but_public_blocks_are_not(self):
        facts = "标题：公司确认资料\n[资料 company-id]\n数据保留期为三个月。"
        self.assertEqual(self.inspect("数据保留期为三个月。", facts=facts), [])
        public = "标题：公开指南\n来源机构：example.org\n精确URL：https://example.org\n数据保留期为三个月。\n用途声明：只做通用参考非本项目事实。"
        self.assertTrue(self.inspect("数据保留期为三个月。", facts=public))
        self.assertEqual(project_fact_text({"requirements": "固定周期三个月", "source_ids": ["uuid"],
                                          "source_version": "18", "statements": [{"kind": "public", "text": "每周备份"}]}), "")

    def test_policy_hash_is_source_sensitive_sha256(self):
        import hashlib
        from pathlib import Path
        import portal.product_content_quality as module
        self.assertEqual(content_quality_policy_hash(), hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())

    def test_reference_quantity_does_not_become_project_parameter(self):
        references = "PostgreSQL文档示例采用每周备份。"
        self.assertEqual(self.inspect("PostgreSQL文档示例采用每周备份。", references=references), [])
        self.assertTrue(self.inspect("项目采用每周备份。", references=references))
        self.assertTrue(self.inspect("本项目参考PostgreSQL文档采用每周备份。", references=references))

    def test_public_documents_embedded_in_background_are_not_project_facts(self):
        facts = {**FACTS, "background": FACTS["background"] + "\n标题：公开指南\n来源机构：example.org\n精确URL：https://example.org\n备份周期为每周。现有系统缺乏统一认证。\n用途声明：只做通用参考非本项目事实。"}
        self.assertTrue(self.inspect("项目备份周期为每周。", facts=facts))
        self.assertTrue(self.inspect("现有系统缺乏统一认证。", facts=facts))

    def test_known_unsupported_status_assertions(self):
        for text in ("现有系统缺乏统一认证。", "现有三套业务系统存在数据孤岛。",
                     "三套业务系统的数据格式存在显著差异。",
                     "目前这三套系统处于独立运行状态，缺乏统一的数据汇聚通道。"):
            with self.subTest(text=text):
                self.assertTrue(any(issue["code"] == "unsupported_project_status" for issue in self.inspect(text)))

    def test_condition_and_evidence_for_existing_status(self):
        self.assertEqual(self.inspect("现有系统是否缺乏统一认证待核实。",
                                      "若现有业务系统存在数据孤岛，可规划统一采集。",
                                      "现有接口格式尚未提供，不代表存在显著差异。"), [])
        self.assertEqual(self.inspect("现有系统缺乏统一认证。", facts="已提供调研结论：现有系统缺乏统一认证。"), [])
        self.assertTrue(self.inspect("现有系统缺乏统一认证。", references="现有系统缺乏统一认证。"))

    def test_arbitration_claim_and_server_count_boundary(self):
        self.assertTrue(any(issue["code"] == "unsupported_capability_claim" for issue in
                            self.inspect("现有两台服务器不足以形成可靠仲裁机制。")))
        self.assertTrue(any(issue["code"] == "unsupported_capability_claim" for issue in
                            self.inspect("现有两台服务器即可实现高可用。")))
        self.assertEqual(self.inspect("不能单凭现有两台服务器的数量证明已实现高可用。",
                                      "现有两台服务器的拓扑与仲裁能力待核实。"), [])

    def test_bare_device_counts_cannot_prove_arbitration_or_high_availability(self):
        for text in ("两台服务器不足以支撑自动故障转移所需的仲裁机制。",
                     "两台服务器即可实现高可用。", "两个节点不足以形成可靠仲裁机制。"):
            with self.subTest(text=text):
                self.assertTrue(any(issue["code"] == "unsupported_capability_claim" for issue in self.inspect(text)))
        self.assertEqual(self.inspect("两台服务器不能单凭数量证明自动高可用。",
                                      "仅凭两台服务器数量不能证明已实现自动高可用。",
                                      "两台服务器的数量本身并不能证明已实现自动高可用。",
                                      "两台服务器的仲裁方案仅为候选并待验证。",
                                      "若拓扑仅含两台服务器，则需验证仲裁能力。",
                                      "PostgreSQL文档讨论两台服务器不足以形成可靠仲裁的特定故障模型。"), [])

    def test_named_item_quantity_matches_before_or_after_equipment_name(self):
        facts = {"items": [{"name": "测试设备", "quantity": "2", "unit": "台"}]}
        self.assertEqual(self.inspect("沿用清单中2台测试设备。", "沿用清单中两台测试设备。", facts=facts), [])
        self.assertTrue(self.inspect("沿用清单中2台交换机。", facts=facts))
        self.assertTrue(self.inspect("沿用清单中3台测试设备。", facts=facts))
        self.assertTrue(self.inspect("配置测试设备时容量为2TB。", facts=facts))

    def test_metadata_identifiers_are_not_body(self):
        uuid = "860a3e2c-7328-448f-a935-e1bb9bddc102"
        self.assertEqual(inspect_content_quality([
            {"text": "方案支持权限控制和审计。", "source_ids": [uuid], "id": "chapter-1-overview"}
        ], project_facts=FACTS), [])
        issues = self.inspect(f"来源UUID为{uuid}，见chapter-1-overview。")
        self.assertEqual({issue["code"] for issue in issues}, {"body_source_identifier"})
        self.assertEqual(len(issues), 2)

    def test_issues_preserve_full_paragraph_and_actionable_claim(self):
        text = "说明" * 2000 + "。采集最近三个月数据。"
        issues = self.inspect("正常段落。", text)
        self.assertEqual(issues[0]["paragraph_index"], 1)
        self.assertEqual(issues[0]["paragraph"], text)
        self.assertEqual(issues[0]["claim"], "采集最近三个月数据")
        self.assertIn("三个月", issues[0]["correction"])

    def test_rules_require_actual_scope_and_authoritative_length(self):
        self.assertIn("中文和阿拉伯数字", generation_quality_rules())
        self.assertIn("低基数本身不是导致大量小文件的通用理由", generation_quality_rules())
        self.assertIn("PostgreSQL表空间", generation_quality_rules())
        self.assertIn("Kafka Connect具备恰好一次处理能力的支持路径", generation_quality_rules())
        self.assertIn("repeat_interval", generation_quality_rules())
        self.assertIn("sample_truncated", content_review_prompt())
        self.assertIn("source_ids", content_review_prompt())
        self.assertIn("权威全文计数", content_review_prompt())
        self.assertIn("正式生产割接前完成验证", content_review_prompt())

    def test_generation_rules_default_missing_runtime_values_and_roles_to_confirmation(self):
        for prompt in (generation_quality_rules(), content_review_prompt()):
            with self.subTest(review=prompt.startswith("独立复核")):
                self.assertIn("对未提供的项目运行数值，默认写确认方法与所需资料字段，不主动给固定候选值", prompt)
                self.assertIn("只有建议或试运行措辞不能擅定每日全量、每小时增量", prompt)
                self.assertIn("逐项写周期待确认、所需字段与验证方法", prompt)
                self.assertIn("已有设备总数量不代表用途拆分、主备或冷热部署已确认", prompt)
                self.assertIn("每部分职责必须有项目依据", prompt)
                self.assertIn("否则明确该职责未确认并说明确认步骤", prompt)
                self.assertIn("来源可核验且明确归属公开文档的标准或软件版本编号仍可正常引用", prompt)
                self.assertIn("该编号不能作为项目运行数值的依据", prompt)
                self.assertNotIn("三套内部业务系统", prompt)
                self.assertNotIn("两台数据服务器", prompt)

    def test_statement_evidence_rejects_marked_public_references(self):
        self.assertEqual(self.inspect("现有系统缺乏统一认证。", facts={
            "statements": [{"text": "现有系统缺乏统一认证。"}]
        }), [])
        self.assertTrue(self.inspect("现有系统缺乏统一认证。", facts={
            "statements": [{"kind": "public_reference", "text": "现有系统缺乏统一认证。"}]
        }))

    def test_tiny_edits_of_long_previous_paragraph_are_not_new_content(self):
        original = (
            "数据采集方案需基于接口调研结果确定连接方式，核实源系统是否支持增量标识和稳定读取视图。"
            "对权限不足、网络中断、字段调整和重复提交分别记录可核验的异常事件，保留关联线索并交由业务方确认。"
            "在故障恢复验证中观察采集端的状态记录、目标端的数据一致性及失败处理路径，结果应形成可追踪的检查记录。"
            "不能将组件部署成功直接等同于端到端无丢失，需验证数据边界、偏移持久化和重放后的幂等写入行为。"
            "未提供的数据规模及接口负载需要在调研后评估，执行时间和验收阈值仍须业务确认。"
        )
        for changed in (original, "二、" + original.replace("确认", "核实", 1), " \n".join(original),
                        original.replace("目标端", "目的端", 1)):
            with self.subTest(changed=changed[:20]):
                self.assertEqual(inspect_repeated_content([changed], previous=["一、" + original])[0]["code"],
                                 "near_duplicate_content")
        reasonable_new_design = (
            "权限审计方案应先识别数据资源、责任角色与授权审批路径，逐项核对接口、导出和管理操作对应的最小授权。"
            "新增账户和角色变更须形成审批证据，撤销权限后验证原凭据无法继续执行受限操作。"
            "检查日志是否包含操作主体、资源范围与执行结果，并验证敏感凭据未被写入日志。"
            "审计记录的留存要求需由业务和合规负责人确认，记录的读取权限、保护方式与删除流程应形成可验证的检查步骤。"
            "对越权访问测试应覆盖跨角色资源请求、直接调用隐藏接口和权限撤销后的再次请求，发现异常后记录整改责任与复测结果。"
        )
        self.assertEqual(inspect_repeated_content([reasonable_new_design], previous=[original]), [])

    def test_short_shared_headings_and_sentences_are_not_near_duplicate_failures(self):
        self.assertEqual(inspect_repeated_content(["第一阶段需求调研", "数据规模待确认。"],
                                                  previous=["第一阶段需求调研", "数据规模待确认。"]), [])

    def test_long_near_copy_uses_full_text_and_current_batch_indices(self):
        original = "权限需结合实际业务职责核实，审计结果应保留关联线索。" * 300
        issues = inspect_repeated_content([original, original.replace("实际", "具体", 1)])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["paragraph_index"], 1)
        self.assertEqual(issues[0]["paragraph"], original.replace("实际", "具体", 1))

    def test_actual_model_partial_copies_in_previous_and_current_batch(self):
        # Original reviewed chapter, not dependent on a mutable runtime snapshot.
        pairs = [
            ('在数据接入层设计中，重点解决三套业务系统与平台之间的数据流向标准化问题。由于未提供具体的系统接口规范和网络拓扑详情，当前方案建议采用模块化适配器模式处理异构数据源。根据Apache Kafka官方文档关于Connect组件的说明，框架提供源连接器“恰好一次”的基础支持，但不会默认保证本项目的端到端一致性；具体链路仍需核实连接器能力、运行模式、事务配置及目标写入和幂等去重机制。因此，在设计接口标准时，必须明确每个业务系统的偏移量管理策略、写入事务机制及幂等去重逻辑。若未来选用消息队列中间件，需特别注意分布式模式下的配置要求，确保源连接器能够准确记录读取位置，并在目标库写入失败时支持重试而不产生重复数据。此部分的具体实现细节、接口协议版本及数据格式定义均标记为待确认事项，需在详细设计阶段结合各业务系统的实际输出能力进行适配。',
             '在数据接入层的接口标准化设计中，必须明确三套内部业务系统与合成数据平台之间的交互契约。鉴于当前未提供具体的系统接口文档、网络拓扑及数据格式规范，本章节仅提出基于通用最佳实践的接口设计原则，具体协议版本、字段映射规则及传输加密方式均标记为待确认事项。根据Apache Kafka官方文档关于Connect组件的说明，框架提供源连接器“恰好一次”的基础支持，但不会默认保证本项目的端到端一致性；具体链路仍需核实连接器能力、运行模式、事务配置及目标写入和幂等去重机制。因此，在设计接口标准时，必须明确每个业务系统的偏移量管理策略、写入事务机制及幂等去重逻辑。若未来选用消息队列中间件作为数据传输载体，需特别注意分布式模式下的配置要求，确保源连接器能够准确记录读取位置，并在目标库写入失败时支持重试而不产生重复数据。此外，接口设计应遵循“最小权限”原则，仅开放必要的数据字段，避免全量数据暴露带来的安全风险。对于非结构化或半结构化数据，建议在接入层引入初步的模式识别与校验模块，但具体的解析算法、容错阈值及异常数据处理流程需结合各业务系统的实际输出能力进行适配。由于缺乏具体的服务器硬件配置参数（如CPU、内存、磁盘IO能力），无法量化评估其承载三套业务系统并发写入的性能瓶颈，相关容量规划指标暂列为待确认项。所有接口定义需在详细设计阶段形成正式的接口规格说明书，并经项目技术负责人、系统集成商及业务系统开发团队共同评审后方可实施。'),
            ('存储计算层是架构的核心，负责数据的持久化存储与初步处理。现有条件仅提供两台数据服务器，这一资源限制对高可用设计提出了严峻挑战。参考PostgreSQL官方文档关于主备故障切换的论述，简单的双机部署并不能自动等同于高可用集群。参考文档指出故障切换需外部检测和明确的旧主隔离，可评估见证节点等辅助判定方式；本项目具体机制及额外资源条件待确认。在当前两机环境下，可评估一主一备的候选部署方式，但心跳检测只提供故障线索，不能单独证明旧主已失去写入能力；网络分区等场景下须验证故障判定、旧主隔离和复制状态，无法确认安全自动切换条件时，应采用经授权且先确认旧主隔离的人工切换预案，所需机制与资源均待确认。同机房主备的高可用设计不能替代机房级灾难恢复或备份恢复体系。RPO（恢复点目标）与RTO（恢复时间目标）须由业务确认，分别通过可恢复数据位置及恢复至服务可用的全过程演练核验；复制延迟、一致性级别及恢复后的数据校验流程也需制定预案，不预先承诺达标。由于缺乏具体的服务器硬件配置参数（如CPU、内存、磁盘IO能力），无法量化评估其承载三套业务系统并发写入的性能瓶颈，相关容量规划指标暂列为待确认项。',
             '存储计算层的设计核心在于如何在仅有的两台数据服务器资源约束下，实现数据的持久化存储与高可用保障。参考PostgreSQL官方文档关于主备故障切换的论述，简单的双机部署并不能自动等同于高可用集群。参考文档指出故障切换需外部检测和明确的旧主隔离，可评估见证节点等辅助判定方式；本项目具体机制及额外资源条件待确认。在当前两机环境下，可评估一主一备的候选部署方式，但心跳检测只提供故障线索，不能单独证明旧主已失去写入能力；网络分区等场景下须验证故障判定、旧主隔离和复制状态，无法确认安全自动切换条件时，应采用经授权且先确认旧主隔离的人工切换预案，所需机制与资源均待确认。同机房主备的高可用设计不能替代机房级灾难恢复或备份恢复体系。RPO（恢复点目标）与RTO（恢复时间目标）须由业务确认，分别通过可恢复数据位置及恢复至服务可用的全过程演练核验；复制延迟、一致性级别及恢复后的数据校验流程也需制定预案，不预先承诺达标。由于缺乏具体的服务器硬件配置参数，无法量化评估其承载三套业务系统并发写入的性能瓶颈，相关容量规划指标暂列为待确认项。在存储结构上，建议采用分层存储策略，热数据存放于高性能磁盘，冷数据归档至低成本存储介质，但具体的存储分级标准、数据生命周期管理策略及备份恢复频率需结合业务需求进一步调研确认。同时，为了支持后续扩展，存储层应采用分片或分区策略，以分散单点压力，但具体的分片键选择、路由规则及再平衡机制需待现场勘测后编制详细的技术规格书。所有存储配置变更均需经过严格的测试验证，确保不影响现有服务的稳定性。'),
        ]
        self.assertEqual([(len(a), len(b)) for a, b in pairs], [(365, 612), (493, 655)])
        for original, changed in pairs:
            for current, previous, index in (([changed], [original], 0),
                                              ([original, changed], [], 1)):
                with self.subTest(lengths=(len(original), len(changed)), index=index):
                    issues = inspect_repeated_content(current, previous=previous)
                    self.assertEqual(len(issues), 1)
                    issue = issues[0]
                    self.assertEqual(issue['code'], 'partial_duplicate_content')
                    self.assertEqual(issue['paragraph_index'], index)
                    self.assertEqual(issue['paragraph'], changed)
                    for block in issue['claim'].split(' … '):
                        self.assertIn(block, original.replace(' ', ''))
                        self.assertIn(block, changed.replace(' ', ''))
                    self.assertGreaterEqual(len(issue['claim']), 180)
                    self.assertIn('保留本段独有内容', issue['correction'])

    def test_partial_copy_thresholds_and_normalisation(self):
        for size, padding, rejected in ((179, 40, False), (180, 40, True),
                                        (180, 420, False), (210, 390, True),
                                        (209, 391, False)):
            shared = ''.join(chr(0x4E00 + i) for i in range(size))
            original = '甲' * padding + shared
            changed = shared + '乙' * padding
            for current, previous in (([changed], [original]), ([original, changed], [])):
                with self.subTest(size=size, padding=padding, previous=bool(previous)):
                    issues = inspect_repeated_content(current, previous=previous)
                    self.assertEqual(bool(issues), rejected)
                    if rejected:
                        self.assertEqual(issues[0]['code'], 'partial_duplicate_content')
        shared = ''.join(chr(0x4E00 + i) for i in range(180))
        self.assertTrue(inspect_repeated_content(['二、' + ' '.join(shared) + '乙' * 80],
                                                previous=['一、' + '甲' * 80 + shared]))

    def test_partial_duplicate_guard_only_reads_body_not_metadata(self):
        shared = '公开参考规范仅供通用说明。' * 30
        self.assertEqual(inspect_repeated_content([
            {'text': '乙' * 260, 'source_ids': [shared], 'chapter_id': shared},
        ], previous=[{'text': '甲' * 260, 'source_ids': [shared], 'chapter_id': shared}]), [])
        self.assertEqual(inspect_repeated_content([
            {'text': '乙' * 260, 'source_ids': [shared]},
        ], previous=[{'source_ids': [shared], 'chapter_id': shared}]), [])
        issues = inspect_repeated_content([
            {'text': shared + '乙' * 80, 'source_ids': ['new']},
        ], previous=[{'text': '甲' * 80 + shared, 'source_ids': ['old']}])
        self.assertEqual(issues[0]['code'], 'partial_duplicate_content')

    def test_bounded_aggregate_copy_requires_long_blocks_and_high_coverage(self):
        for sizes, padding, rejected in (((164, 59), 100, True),
                                         ((164, 59), 300, False),
                                         ((100, 100, 100), 40, False),
                                         ((130, 49, 49), 40, False),
                                         ((164, 59), 2200, False)):
            blocks = [''.join(chr(0x4E00 + i * 300 + j) for j in range(size))
                      for i, size in enumerate(sizes)]
            original = ('甲' * 8).join(blocks) + '丙' * padding
            changed = ('乙' * 8).join(blocks) + '丁' * padding
            for current, previous in (([changed], [original]), ([original, changed], [])):
                with self.subTest(sizes=sizes, padding=padding, previous=bool(previous)):
                    issues = inspect_repeated_content(current, previous=previous)
                    self.assertEqual(bool(issues), rejected)
                    if rejected:
                        self.assertEqual(issues[0]['code'], 'partial_duplicate_content')


CHAPTER_CONTRACT_APPROVED = [
    {"id": "chapter-1-overview", "title": "第一章 项目背景与建设目标"},
    {"id": "chapter-2-current-state-analysis", "title": "第二章 现状分析与需求梳理"},
    {"id": "chapter-3-architecture-design", "title": "第三章 总体技术架构设计"},
    {"id": "chapter-4-data-collection-scheme", "title": "第四章 数据采集技术方案"},
    {"id": "chapter-5-data-storage-scheme", "title": "第五章 数据存储与管理方案"},
    {"id": "chapter-6-data-quality-monitoring", "title": "第六章 数据质量监控体系"},
    {"id": "chapter-7-security-and-audit", "title": "第七章 安全权限与审计机制"},
    {"id": "chapter-8-implementation-validation", "title": "第八章 实施路径与验证计划"},
]


class ChapterContractTests(SimpleTestCase):
    def check(self, paragraphs, current="chapter-1-overview"):
        return inspect_chapter_contract(
            paragraphs,
            approved_chapters=CHAPTER_CONTRACT_APPROVED,
            current_chapter_id=current,
        )

    def test_chapter_contract_current_chapter_chinese_ordinal_may_be_bare(self):
        self.assertEqual([], self.check(["本章（第一章）说明建设背景。"]))

    def test_chapter_contract_current_chapter_arabic_ordinal_may_be_bare(self):
        self.assertEqual([], self.check(["参见第1章，本节先交代背景。"]))

    def test_chapter_contract_cross_chapter_chinese_ordinal_requires_full_approved_title(self):
        self.assertEqual(
            [],
            self.check(["详见第五章 数据存储与管理方案中的恢复设计。"]),
        )

    def test_chapter_contract_cross_chapter_arabic_ordinal_ignores_whitespace_without_duplicate_ordinal(self):
        self.assertEqual(
            [],
            self.check(["详见第 5 章   数据 存储与管理方案。"]),
        )

    def test_chapter_contract_v5_article_style_wrong_mapping_is_rejected_by_actual_ordinal(self):
        issues = self.check([
            "第二章 接口方案介绍系统接入方式。",
            "第三章 数据存储与管理方案介绍目标数据库。",
            "第四章 部署架构说明机房配置。",
            "第五章 安全权限与审计机制说明访问控制。",
        ])
        self.assertEqual(
            ["approved_chapter_reference_mismatch"] * 4,
            [issue["code"] for issue in issues],
        )
        self.assertEqual([0, 1, 2, 3], [issue["paragraph_index"] for issue in issues])

    def test_chapter_contract_incomplete_or_wrong_cross_chapter_title_is_rejected(self):
        issues = self.check([
            "请看第七章。",
            "请看第七章 权限设计。",
        ])
        self.assertEqual(
            ["approved_chapter_reference_mismatch"] * 2,
            [issue["code"] for issue in issues],
        )
        self.assertIn("第七章 安全权限与审计机制", issues[0]["correction"])

    def test_chapter_contract_unknown_project_ordinal_is_reported(self):
        issues = self.check(["按第九章要求执行后续安排。"])
        self.assertEqual("unknown_approved_chapter_reference", issues[0]["code"])
        self.assertEqual(0, issues[0]["paragraph_index"])

    def test_chapter_contract_adjacent_official_source_chapter_citation_is_preserved(self):
        self.assertEqual(
            [],
            self.check(["可参考官方文档中的第十八章，理解其通用原则。"]),
        )

    def test_chapter_contract_adjacent_official_document_without_particle_is_preserved(self):
        self.assertEqual([], self.check(["可参考官方文档第十八章，理解其通用原则。"]))

    def test_chapter_contract_distant_document_mention_does_not_exempt_project_chapter(self):
        issues = self.check(["方案参考过官方文档。项目执行时仍按第十八章的流程处理。"])
        self.assertEqual("unknown_approved_chapter_reference", issues[0]["code"])

    def test_chapter_contract_first_observed_split_quote_is_located_without_repairing(self):
        paragraphs = [
            "该目标不能由",
            "统一",
            "这一目标预设具体接口已经具备。",
        ]
        issues = self.check(paragraphs)
        fragment = next(issue for issue in issues if issue["code"] == "fragmented_quoted_paragraph")
        self.assertEqual(0, fragment["paragraph_index"])
        self.assertIn("统一", fragment["claim"])
        self.assertIn("返回本批全部完整正文", fragment["correction"])
        self.assertEqual("该目标不能由", paragraphs[0])

    def test_chapter_contract_second_observed_split_quote_is_located(self):
        paragraphs = [
            "子目标中",
            "在两台现有数据服务器资源约束下确定数据组织方式",
            "的表述需回退修正后再确认。",
        ]
        issues = self.check(paragraphs)
        fragment = next(issue for issue in issues if issue["code"] == "fragmented_quoted_paragraph")
        self.assertEqual(0, fragment["paragraph_index"])
        self.assertIn("数据组织方式", fragment["claim"])

    def test_chapter_contract_all_fragment_triplets_in_the_batch_are_reported(self):
        paragraphs = [
            "不能由",
            "统一",
            "这一方案待确认。",
            "子目标中",
            "在两台现有服务器约束下确定数据组织方式",
            "的表述需修正。",
        ]
        fragments = [
            issue for issue in self.check(paragraphs)
            if issue["code"] == "fragmented_quoted_paragraph"
        ]
        self.assertEqual([0, 3], [issue["paragraph_index"] for issue in fragments])
        self.assertTrue(all("返回本批全部完整正文" in issue["correction"] for issue in fragments))

    def test_chapter_contract_single_dangling_function_phrases_are_reported(self):
        dangling = ["关于", "依据", "通过", "由于", "为了", "鉴于", "根据", "不能由", "这一"]
        for phrase in dangling:
            with self.subTest(phrase=phrase):
                issues = self.check(["完整的前置说明。", phrase, "后续内容仍需核实。"])
                match = next(issue for issue in issues if issue["code"] == "dangling_paragraph")
                self.assertEqual(1, match["paragraph_index"])
                self.assertEqual(phrase, match["claim"])

    def test_chapter_contract_dangling_phrase_match_ignores_internal_whitespace_and_sentence_endings(self):
        paragraphs = ["完整句子。", " 关 于 ！ ", "依据；", "不能 由?", "仍需核实。"]
        before = list(paragraphs)
        issues = self.check(paragraphs)
        dangling = [issue for issue in issues if issue["code"] == "dangling_paragraph"]
        self.assertEqual([1, 2, 3], [issue["paragraph_index"] for issue in dangling])
        self.assertEqual([" 关 于 ！ ", "依据；", "不能 由?"], [issue["claim"] for issue in dangling])
        self.assertEqual(before, paragraphs)

    def test_chapter_contract_dangling_paragraph_issues_keep_the_repair_contract(self):
        paragraphs = ["资源配置", "关于", "通过"]
        issues = [issue for issue in self.check(paragraphs) if issue["code"] == "dangling_paragraph"]
        self.assertEqual([1, 2], [issue["paragraph_index"] for issue in issues])
        self.assertTrue(all(set(issue) == {"code", "paragraph_index", "claim", "correction"}
                            for issue in issues))
        self.assertTrue(all("返回本批全部完整正文" in issue["correction"]
                            and "不会自动重写或合并" in issue["correction"] for issue in issues))

    def test_chapter_contract_dangling_guard_preserves_short_titles_sentences_lists_and_prose(self):
        paragraphs = [
            "资源配置", "统一", "验收", "已确认。", "待确认。", "一、关于数据来源的说明。",
            "根据现有接口清单，逐项核实字段与责任人。", "这一方案覆盖接口盘点。",
        ]
        self.assertEqual([], [issue for issue in self.check(paragraphs)
                              if issue["code"] == "dangling_paragraph"])

    def test_chapter_contract_missing_outline_skips_reference_check_but_keeps_fragment_check(self):
        issues = inspect_chapter_contract(
            ["可参见第九章的说明。", "不能由", "统一", "这一判断仍需核实。"],
            approved_chapters=None,
        )
        self.assertEqual(["dangling_paragraph", "fragmented_quoted_paragraph"], [issue["code"] for issue in issues])
        self.assertEqual(1, issues[0]["paragraph_index"])

    def test_chapter_contract_headings_sentences_colon_lists_and_complete_quotes_are_not_fragments(self):
        paragraphs = [
            "以下内容包括：",
            "第一节 数据采集方案",
            "数据采集方案",
            "该方案覆盖接口盘点。",
            "部署步骤如下：",
            "一、确认系统边界。",
            "完整短句。",
            "补充说明该短句的范围。",
            "参考内容如下：",
            "“官方文档中的第十八章只提供一般性说明。”",
            "该引用不表示项目已完成配置。",
        ]
        self.assertEqual([], self.check(paragraphs))

    def test_chapter_contract_issue_shape_is_stable_and_input_is_unchanged(self):
        paragraphs = ["引用第九章内容。"]
        before = list(paragraphs)
        issues = self.check(paragraphs)
        self.assertEqual(before, paragraphs)
        self.assertEqual(
            {"code", "paragraph_index", "claim", "correction"},
            set(issues[0]),
        )
