# AI-T11 / AI-AC11：显式生命周期结果与原 Excel 后来缺失

实际时间：2026-10-18T05:56:40.129210+08:00 至 05:56:49.552920+08:00。本单元仅补此前没有直接验证的三个隔离场景；不修改生产代码、旧测试、前端、服务或所属资料库。

## 已有证据与本次范围

先读根 AGENTS、SDD README、当前验收与 [05:42 缺口核账](../AI-T15/2026-10-18-0542-acceptance-gap-triage.md)，核查 `baichuan_research.py`、现有研究九例、Excel normalizer/converter/importer 以及 legacy 补链模块和测试。[原固定清单证据](2026-10-17-fixed-manifest-queue.md)已经覆盖新增 ID、独立增量、分批、恢复、固定版本及删除保护；[原来源补链证据](../AI-T05/2026-10-17-legacy-source-evidence-links.md)覆盖实际1460条补链和重放。没有把这些历史记录称作本次实测，也未重复运行它们。

现有研究服务支持显式 `merged`、`removed` 结果，保留完整 outcome/checkpoint 和冻结 `company_versions`；未提供企业合并业务入口，也不自动验证或推断目标主体。以下测试只证明记录与历史保护能力，不声称执行了真实企业合并。

## 新增三个实质性检查

新增独占模块 `services/business/backend/portal/tests/test_baichuan_manifest_source_lifecycle.py`，使用真实服务、ORM、租约及临时文件 SQLite；不替换数据库、导入、normalizer、补链或覆盖报告的输出。

1. `test_explicit_merged_outcome_retains_target_baseline_and_fixed_denominator`：建立两家合成企业和旧快照，固定清单后发生一个显式版本变更；经真实 claim/record_batch 保存 merged 与明确目标 ID checkpoint。重复同一结果不增加尝试；保留 baseline=2、observed=3 和 changed=true。完成另一项后分母仍2家/2字段，merged单列，已核实0；两家企业保留，电话原值及旧快照整行不变。
2. `test_explicit_removed_is_terminal_unverified_history_not_physical_deletion`：显式 removed 结果覆盖两字段，条目及冻结版本均保留，终态完成1家但核实字段0，verification仍unverified。企业整行不变，物理删除仍触发 ProtectedError。这里的 removed 是研究结果，不能冒称企业已删除。
3. `test_moved_original_excel_preserves_import_evidence_manifest_and_snapshot`：写入实际8工作表合成原 XLSX，经真实 normalizer/converter 生成受审核映射，再生成转换表并真实 preview/apply 导入，映射旧资质并补链。保存原表 SHA、总表和分类表定位、完整 normalized JSON，再创建研究清单与旧快照。实际将原表和转换表改名移开；fresh normalize/preview 分别明确抛 FileNotFoundError。数据库保存的八类历史记录整行保持（Company、CompanyQualification、Certificate、Evidence、Revision、Manifest、MatchSnapshot、Job）；同清单重建不新增，补链重放 created=0/already_linked=1。来源 excerpt、原表 hash 引用和两处定位仍可读取，证据仍unverified、identity_verified=false，核实字段0。

第三例仅使用新建临时目录和合成资料，不移动用户原 Excel。它证明缺失不删除既有数据库来源，不代表可以从缺失文件重新提取内容，亦不代表旧来源已核实。

## 实际命令与结果

```text
.runtime/company-test/python/Scripts/python.exe -X utf8 .runtime/baichuan-ai-local/night-acceptance-20261018/manifest-source-lifecycle-0552/run_checks_r2.py

# 上述受限 runner 实际执行：
.runtime/company-test/python/Scripts/python.exe -X utf8 scripts/baichuan/check_backend.py portal.tests.test_baichuan_manifest_source_lifecycle
```

最终 **3 tests / 1.063s / OK / 零跳过**；runner墙时9.424秒，Django system check零问题。受限 runner 清除继承 PORTAL 配置，使用新临时 file SQLite，180秒封顶。每例明确禁止 socket DNS/connect 和 worker/runtime 模型接口，并断言其均未调用；真实所属数据库连接0、HTTP/模型0。11个新测试/所依赖业务与旧测试输入前后 SHA 全部一致。

首轮为2通过、1 ERROR：新夹具把 normalizer detail 的完整 `cells` 字典放入只允许受限定位键的 `section`，现有服务正确拒绝。只修新夹具，将实际 detail 的 sheet/row 显式投影；完整原 cells 继续归档并断言。不削减业务校验，不修改生产模块。首轮 intent、log、FAIL receipt 全保留，最终结果另存 attempt-2。

私有目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/manifest-source-lifecycle-0552/`。

| 固定产物 | SHA256 |
| --- | --- |
| 新测试模块 | `40bf8e82d5ab0f392c03ea65f65da79098fa04554286ee4b90e04105492c055b` |
| 首轮 receipt（保留 ERROR） | `2758762e17a597230e9c613a6d4ca2149dbbae00aeb90c13771c4d38a5f72a56` |
| attempt-2/receipt.json | `d4484d7dae5b95a9144347c3dd430d6c8fd0f596e99a912cd56e9a17e8f4ba58` |
| attempt-2/test.log | `396774031d1f86afe4f285d09172dccfbe6684cc663bed92d422bc31144f556a` |

## 验收限制与恢复点

这里只补 AI-AC11 的三项确定性生命周期检查，属于隔离后端证据，不能改写成真实浏览器验收或全库研究完成。实际清单全12字段的可靠来源补齐、未核实资质的独立发证核验仍须按真实研究状态计量。没有新增企业合并入口；目标 checkpoint 是维护者显式提供的追溯记录，不是系统确认法律合并的结论。既有原 Excel 真实恢复与1460补链记录按原证据保持，旧事故和首轮错误均不覆盖。

新模块已冻结并交主执行者纳入其下一轮统一回归；本页不预先声明该统一回归通过，不修改共享任务、检查点或总体状态。无需重跑本单元或重新读取原件即可恢复：核对上述新模块与 receipt SHA，再按实际未完成的全库研究继续。
