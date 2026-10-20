# 原始资质声明的增量证据补链

2026-10-17（Asia/Shanghai）。关联 AI-T03/AI-T05/AI-T07/AI-T14/AI-T15。只涉及后端、维护脚本与独立证据，前端保持冻结。用户原表所属本地库1283企业/1460旧资质；历史官网研究未恢复。

## 实现与隔离验证

新增 `services/business/backend/portal/baichuan_legacy_evidence.py`，显式维护权限、正整数企业版本、企业与证书锁、锁后/预检后再次权限校验。旧声明与原mapped_declaration完整一致、证书仍未核实、非空source才补链。显式sheet/row来源映射要求source逐字和SHA256一致，拒绝未知ID、无效定位、伪核验字段；服务不自行猜测定位。

新增 Evidence 为legacy_import/unverified，identity_verified=false，verified_on=null，完整保留原source并记录hash。追加legacy_source_evidence_link修订及审计，supersedes保留原mapped_declaration；证书仅更新证据/修订指针，未升级核实。公司、旧资质、人员、既有修订与旧结果快照不改。重放必须核对同scope/company/legacy ID/source/hash/追加链/显式定位，其他已有证据留原值并报冲突，不能假算幂等成功。

专用9例加既有facts/conditions共 **27 tests / 11.849s / OK**，Django system check 0 issues；实际使用company-test Python，测试专用SQLite配置，清除继承PORTAL_DB*/PG*变量，Django建立独立内存测试库，未连接本地资料库或外网。覆盖人工值/旧快照/修订链保留、正确来源定位、只读/撤权/版本拒绝、原声明变更、错误部署证据、幂等、空来源、审计失败事务回滚，以及unknown仍unknown但带来源ID。早期测试夹具漏填result_revision及一次不存在的测试模块名已修正，以上只引用最终实际通过命令。

```text
manage.py test portal.tests.test_baichuan_legacy_evidence portal.tests.test_baichuan_facts portal.tests.test_baichuan_conditions --verbosity 1
```

## 所属本地原表库实际执行

脚本 `scripts/baichuan/backfill_legacy_source_evidence.py`，默认inert实测0写入/0联网。执行条件为显式--execute与原件SHA256；校验owned标记/SQLite路径、原件与留存副本hash、已恢复receipt、1283企业ID集合、1460旧资质ID及全部原值。源定位来自已核账normalized claims，复用现有converter及importer `_source`（包括中间XLSXhash/行号/备注）精确重建完整字符串，不截尾、不模糊归并。

首次预检发现初版未计入importer追加的来源尾注而安全停止，**尚未写入企业或证据**；修正完整来源重建后全量1460条预检零冲突。20:16:44新建SQLite在线备份，quick_check=ok，备份SHA256 `c3c0697e49c907d0cda37f3dcd93309b031c2879d5332b6bcb111bb9fbaceabc`。随后每企业事务，私有plan/state逐家保存；进程退出释放文件锁，恢复核对原备份hash与原表摘要，最终计数从持久DB重建，避免提交后检查点未落盘造成少算。

```text
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/backfill_legacy_source_evidence.py --execute --source-sha256 220ec53ebe6a87263978f297891107700070d07588a4532b62ba884d64f68f07
```

首次完成：1460新证据、1460追加修订、1460证书补链、1283企业，已核实证据0，模型/网络调用0。同命令实际重放：新增0、already_linked1460、模型0，原目录摘要一致。私有备份、plan、state及replay收据位于 `.runtime/baichuan-ai-local/source-evidence-220ec53ebe6a/`。全字段公司/旧资质/人员摘要前后一致：`724750bb86495c671d0135e271ac6d4563f788ff4a0fae815a9e4312301d093d`。

## 修复后匹配及实际 XLSX

直接复用原NL已解析条件只读执行deterministic match，仍0确认/1283候选，411家电子原声明具有来源ID，未知未变满足。读取一个已存在的后续快照API，首屏3条来源具有summary及detail的sheet/row、excerpt非空、verified_on=null。下载12036字节XLSX，企业结果0、待核实候选10、逐项依据10；实际openpyxl核对来源标题、未核实日期和sheet/row定位，无公式单元格。原NL固定快照和原两份XLSX保持不变，不能假称旧文件自动补齐来源。

**验收执行事故：本轮模型预算未通过。** 最初NL调用为授权的一次（日志6）；补链后的私有“确定性验收”脚本save_job持久化conditions后，漏刷新内存job，process_query读到旧空checkpoint，意外再次调用模型（日志7，success，4589ms，789/233tokens）。本单元累计新增2次，超出明确上限1。立即向主执行者报告、停止新查询，完整保留调用日志/失败脚本/新快照；没有发企业名册、电话或附件，新请求仍为泛化条件说明。不能将该快照称为零模型或与原条件完全相同：它额外含unresolved说明。后续仅复用原条件做只读规则评估、读取已有快照与导出，没有再调用模型或搜索。私有脚本已加refresh及拒绝任何模型调用的保护，但修正后脚本未重跑，不宣称已执行通过。

私有 `public-query-acceptance/repaired-source-receipt.json` 明确 `source_links_passed_model_budget_failed`、累计模型2/授权1，保留失败边界；源证据补链/幂等本身通过，完整端到端预算子项不能标PASS。源字段独立核实仍0，全库研究没有据此推进；搜索/研究/事实写入全局保持关闭，未改远程生产环境。
