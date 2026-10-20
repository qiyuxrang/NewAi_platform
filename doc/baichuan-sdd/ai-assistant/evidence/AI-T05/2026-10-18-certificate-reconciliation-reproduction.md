# AI-T05 证书范围隔离与幂等边界：修复前复现

2026-10-18。本单元仅新增 `portal/tests/test_baichuan_certificate_reconciliation.py`，未修改核心逻辑、共享任务状态、前端或服务。没有接入实际资料库、业务模型或公网；全部企业、证号和发证资料为合成夹具，不代表真实核实。测试内禁止 DNS、create_connection 和 socket.connect。

实际命令（仓库根目录）：

```powershell
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/check_backend.py portal.tests.test_baichuan_certificate_reconciliation
```

运行器清除继承的 PORTAL 配置，在独立 TemporaryDirectory 创建文件 SQLite 测试库及私有存储，测试后销毁。实际结果 **14 tests / 4.282s，9 FAIL、5 PASS、0 ERROR**；Django system check 0 issues。退出码1是本次明确保留的真实缺陷复现，不是已修复通过。原日志私有保存于 `.runtime/baichuan-ai-local/certificate-reconciliation-20261018/before-fix-tests.txt`。

| 用例 | 预期 | 实际 |
| --- | --- | --- |
| 另一 scope 的完全相同证书 | 本 scope 独立追加 | FAIL：返回另一 scope 旧修订 |
| 另一 scope 同证号、不同等级 | 本 scope 独立追加 | FAIL：误判 conflict |
| 同 scope、同号、issuer 不同 | 新冲突修订、保留旧证 | FAIL：提前返回旧 applied 修订 |
| standard / scope_text / holder_type / holder_company_id / assertion_status 各自不同 | 各自生成冲突，不误幂等 | 5 FAIL：均提前返回旧 applied 修订 |
| 旧记录 unverified，其他值相同 | 不将未核实旧声明当成完整核实重放 | FAIL：提前返回旧 proposed 修订 |
| 同 scope 完整相同且已核实 | 返回同一修订、不增证、不改版本 | PASS |
| 同 scope 同号但日期不同 | conflict、不覆盖旧证 | PASS |
| 同 scope 同号但持有人名称不同 | conflict、不覆盖旧证 | PASS |
| 原人工同等级证号不同 | conflict、人工原号保留 | PASS |
| 无明确 valid_from | proposed/unverified、不生成证书 | PASS |

缺陷位置为 `baichuan_facts.propose_certificate` 的 old 查询及 same 提前返回。same 只比较证号、等级、两日期、holder_name、撤销状态，遗漏完整主体、颁发方、标准、范围、声明状态及核实状态；old 未按来源 scope 隔离。当前失败没有证明实际库受到改写，亦未做真实证书入库。

建议窄修：先排除有明确其他 scope 的证书及来源修订，再执行去重/冲突；不能简单只保留 evidence__scope 匹配而丢弃无证据的人工旧声明。完整去重必须核对完整声明语义、已核实旧状态及本范围有效来源，否则同 scope 同号应保留冲突。保留现有人工保护、权限/版本/开关、日期和来源门槛。本轮不实现 grade-only 豁免。官方查询“有效”不替代明确有效起始及具体范围，不能把“获证日期/发证日期”自行转为 valid_from。

下一步：由主执行者结束保护窗口并授权核心窄修；保持本失败日志，修复后新建日志重跑本模块及既有 facts/legacy-source/matching 专项。该证据不代表修复或实际部署完成。

## 已授权修复规则（实现前记录）

主执行者已结束保护窗口并授权仅修改 facts 与本专项测试。先隔离明确绑定其他 evidence.scope 的旧证书；证书无直接证据时，查来源修订的证据 scope，无来源的人工旧声明仍参与冲突保护。去重比较全部声明字段，并要求新提案有效、旧证书已核实、核实时间存在、旧证据通过本 scope 的现有权威/主体校验、旧应用修订与证据/企业一致；撤销状态 clear 的旧来源亦须保留同日核查依据。不能将旧 proposed/unverified 误当成功的核实重放。同 scope 同号实质变化继续 conflict。原 grade-only 规则、valid_from/主体/范围/来源门槛不放宽，不触碰真实库或服务。以下结果在实际执行后另追加，初始9失败日志冻结保留。

## 修复后专项结果

`baichuan_facts.py` 已按上述规则修改。原14项复现测试加3项防退化（仅修订带其他scope、完全无证据人工同号、无效新证据不得被旧已核实记录吞掉）以及既有 facts/source/matching/API权限/研究安全专项合并执行：**70 tests / 35.260s / OK，0 skip，Django system check 0 issues**。初始9项失败均已转为通过。运行出现既有 staticfiles 目录不存在的 UserWarning，未发生错误或跳过。

```powershell
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/check_backend.py portal.tests.test_baichuan_certificate_reconciliation portal.tests.test_baichuan_facts portal.tests.test_baichuan_legacy_evidence portal.tests.test_baichuan_matching portal.tests.test_baichuan_api_permissions portal.tests.test_baichuan_research_security
```

修复后独立日志为 `.runtime/baichuan-ai-local/certificate-reconciliation-20261018/after-fix-targeted-tests.txt`；修复前日志及收据未改。`git diff --check` 对本单元文件实际通过。实际资料库写入、模型调用、公网请求、服务/前端变更均0。本结果仅证明隔离后端修复；由主执行者另行执行全量回归与是否加载的决策，不代表真实证书核实或资料交付完成。
