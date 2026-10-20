# AI-T04 / AI-T07 确定规则与匹配边界验收

执行日期：2026-10-17。工作区 HEAD `ef1676cd8327d693dab897c45a234ba91413884e` 加本轮未提交代码；使用 Windows Python 3.13.16、Django、临时文件 SQLite。未使用真实企业库、真实模型、公网、前端或运行服务。

## 本轮实际问题及修复

- `company_facts` 过去将只有主键的占位对象传给官网身份核验；已有来源采用 `official_host_name_credit_code` 时因缺 `website_kind` 抛异常。现在传完整当前企业，官网域名改变后旧依据不会继续核实字段。
- 字段修订按最新时间/ID处理，并在直接调用和预加载两条路径都排除私人 `proposed`；最新人工改动不复活旧核验。官网/公开全称方法还须明确包含该字段字面声明，单有企业身份不能证明地区。
- 未来获取/核验时间不能作为当前证据。撤销检查日期须与核验日期一致，并覆盖要求日期；今天的核查不能靠一个未来 `revocation_as_of` 声明确认未来投标日。
- 非空证书持有人名称与企业名称矛盾时，证据保持未核实；集团、制造商、联合体成员、人员、产品及范围不匹配均不能确认投标人。
- 规则须有当前正文核验、正文哈希及定位，搜索摘要/模型输出不能启用规则。损坏的 JSON 等级关系、越出合法等级的映射不会报错或误确认。
- 匹配入口重新读账号；规则安装在取得账号锁后校验权限，保留显式、幂等七类兼容安装。

修改范围仅 `portal/baichuan_matching.py`、`portal/baichuan_rules.py` 与新增 `portal/tests/test_baichuan_matching.py`。没有修改 conditions、assistant、worker、前端或全局配置。

## 实际执行

首轮新14项测试复现失败：unittest记录11个失败断言、4个异常，含一个方法的多个 `subTest`；未将失败记为通过。私有日志 `.runtime/baichuan-ai/matching-before.log`。

修复后14项通过，4.907秒。随后增加字段字面绑定、标准/规则时点、稳定排序的实质用例。

最终命令（仓库根目录）：

```powershell
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan_matching portal.tests.test_baichuan_conditions portal.tests.test_baichuan_assistant.AssistantTests.test_matching_requires_current_evidence_not_legacy_present portal.tests.test_baichuan_assistant.AssistantTests.test_rules_install_requires_maintenance_and_preserves_uncovered_relations portal.tests.test_baichuan_legacy_evidence
```

**实际结果：36 tests，13.020秒，OK，无跳过。** 新匹配模块17项、既有条件8项、既有接口内匹配/规则2项、原来源补链9项。新17项主动禁止并断言未调用 socket连接/DNS/模型网关。私有完整日志 `.runtime/baichuan-ai/matching-final.log`。三个改动 Python 文件 `py_compile` 通过。

验收映射：AI-AC05的精确/同类OR/跨类AND/NOT未知/相反等级方向/版本/未支持类别；AI-AC06的主体与范围；AI-AC07的含边界起止日、未生效、到期、撤销/未知撤销、未来要求日；AI-AC08的硬失败不被偏好抵消、未知保留、稳定排序及后续事实改变不改旧快照。本轮采用真实ORM、持久作业租约与快照，不仅调用纯函数。

## 完成建议及限制

就本轮负责的规则/匹配后端实现，AI-T04、AI-T07已具备可审阅实现与实际隔离证据；由主执行者汇合条件编译代理的结果后决定升级任务状态。本记录不直接修改共享任务状态。

七类精确匹配保持旧契约；生产等级“及以上”当前仅CS有已启用方向依据，其他未覆盖关系明确未知。测试中的相反方向规则标为虚构fixture，不伪称已补齐ITSS等生产标准来源。

单个过期/撤销/等级不符证书只证明该证书不适用，不证明该企业没有其他证书，因此无完整类别核查依据时企业仍为候选；逐项保留证据ID。没有新增发证机构核验适配或将原1460条声明提升为核实。完整文件主体提取、真实模型、UI及实际部署不由本轮隔离结果替代。

性能回归见 [本轮结构化样本](../AI-T16/2026-10-17-matching-boundary-benchmark.json)：1000家热12样本P95 292.526ms；5000家1180.167ms，每次均断言确认/候选各半。仅结构化匹配，不覆盖AI-T16全部慢网/扫描/并发或端到端性能。
