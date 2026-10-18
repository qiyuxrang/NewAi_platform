# AI-T07 / AI-T14 / AI-T15：固定快照证号与XLSX文本读回

时间：2026-10-18T03:07:44.725946+08:00。新增后端代码尚未加载到所属服务；本单元0真实库访问、0模型/网络、0前端和服务操作。Root先更新AI-FR09/plan/AI-AC12具体口径后实施，主验收状态由root统一维护。

## 改动与边界

`baichuan_matching.py`在确定规则判断后新增结果行 `certificate_records`。只冻结该企业自身、证据scope等于当前部署、证据subject.company_id准确对应企业，而且该证书类别与具体资质条件匹配、证据ID实际被该条件引用的记录。未被采用的其他类别、其他企业、其他scope、错主体来源与superseded证书不加入。

冻结证号字符串、证书ID、实际持有人类型/名称/企业ID、类别与原文、等级与原文、颁发方、起止日期、标准/范围、声明/核实/撤销状态、核实时间、来源状态及condition_ids。保存记录不修改匹配结果、不将制造商归投标人、不把未核实字段升级。

`baichuan_exports.py`仅使用固定记录。逐项依据原10列位置保持，从K列追加证书编号及主体/类别/等级/日期/核实等17列。以结果企业ID、当前授权scope、该逐项条件ID、准确来源ID再次关联；合法同一来源多证逐行输出，并计入原工作表上限。证号经过既有文本cell写入，旧快照缺元数据时追加列留白；没有导出时查询当前证书表的fallback。

## 实际隔离检查

执行：

```text
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan_matching portal.tests.test_baichuan_exports portal.tests.test_baichuan_integration_review
```

该入口清除继承PORTAL配置，新临时文件SQLite与storage。最终实际 **58 tests /38.070秒 /OK /0skip**，system check 0 issues。包含原相关模块与新增6项，不与此前321项相加。首轮58项38.105秒有1个新测试fixture错误：辅助函数已有holder默认又传manufacturer而抛TypeError；保留首次失败说明，修正测试构造后完整重跑58项，没有降低业务断言。

新增断言：

| 测试 | 实际结果 |
| --- | --- |
| matching `test_certificate_metadata_is_bound_to_company_scope_category_and_cited_condition` | 仅自身相关类别的001239进入记录；共享evidence的其他类别、外scope、错subject和其他公司证号排除；保留自己的certificate/source/condition ID与issuer |
| matching `test_unverified_manufacturer_metadata_preserves_actual_holder_and_unknown_verdict` | 展示实际manufacturer及其名称/未核实状态，仍candidate、confirmed0 |
| exports `test_actual_snapshot_certificate_numbers_survive_xlsx_and_later_certificate_changes` | 真实ORM证书→matcher→持久snapshot→导出→openpyxl读回001239与公式样式编号，均data_type=s且无hyperlink；前10列位置不变；制造商/未核实/未知均保留。改当前证号/持有人后新导出仍读旧冻结值，原snapshot与旧文件逐字节不变；patch证书manager禁止导出阶段查表 |
| exports `test_legacy_snapshot_does_not_backfill_certificate_numbers_at_export_time` | 旧快照K/L列留白，禁止查当前证书表 |
| exports `test_frozen_metadata_cannot_cross_company_scope_evidence_or_condition` | 伪混入四种不匹配记录均不导出，仅本行自身匹配证号000123与未核实状态 |
| exports `test_certificate_expansion_counts_toward_evidence_sheet_limit` | 一个来源两证不能绕开每表安全行数，分配工作簿前明确拒绝 |

四个改动Python文件 `py_compile` 退出0，`git diff --check`退出0。未进行目标环境真实模型/文件验收，不把本次隔离结果称为已部署。

## 指纹与恢复点

私有目录 `.runtime/baichuan-ai-local/night-acceptance-20261018/certificate-metadata/`：`targeted-r2.log`、`first-run-failure.txt`、`receipt.json`。

- matching SHA：`5ca981f30d619e565a713188572235e0e48750022ee8e6f1b12a5d78290801d6`
- exports SHA：`72e6773dec89fcb2a0f4f0f7d4c49daca40a06bd5718db624f452e4bf793ee55`
- matching测试 SHA：`035ff1c9b8f4a06e83706d8f4f636b5ce13c7c618704eda7f76622591d7df55e`
- exports测试 SHA：`9a5d265b640d95ce6e9c27eab5007ec429e953d435a10d1cad9f1f5ef756213b`
- 最终日志 SHA：`b9b3797ee5d5246b15c3c1a6454de0c2ec2af90d98337cb71f4feed40122ee9e`

相对本单元02:59:37只读核账，28核心仅matching、exports两文件变化。旧321回归与loaded指纹代表原版本；新版本以本次58项为证，root后续决定合并全套检查与backend-only加载。旧快照不回填，当前已存在证书编号为空的企业也不会凭空得到编号。
