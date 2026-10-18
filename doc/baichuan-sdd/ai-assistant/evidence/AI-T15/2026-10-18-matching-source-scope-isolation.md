# AI-T07 / AI-T15：匹配资料的部署 scope 隔离修复

2026-10-18 本地隔离实测。只修改 `baichuan_matching.py`，新增独立 `test_baichuan_matching_scope.py`；未修改原测试、公开证书维护实现、前端、数据库结构或真实库，未调用模型/外网，未重启服务。实际加载由根任务另行完成；此前 360 项回归不代表本修复已验收或已加载。

## 已复现问题

`company_facts` 原来保留其他 evidence.scope 的证书 `verification_status=conflict`，只将证据核实状态降为 unverified。判定器优先检查 conflict，因此其他部署的冲突可压制本部署已有已核实证书，并将其他部署证据 UUID 放入逐项依据。

企业字段修订也在检查来源前占用 `seen`，其他部署的新冲突修订可遮蔽本部署较旧、仍与当前值相同且有有效来源的修订。

先以原代码执行两个真实 ORM 隔离反例，**2 FAIL / 0.623s**，已保留原代码、输入 SHA、命令和失败日志。失败分别为本应确认而 confirmed=0，以及本应使用当前部署已核实城市但实际为 conflict。没有修改断言使旧代码通过。

## 修复范围

- 字段修订明确有其他 scope 来源时，在 `seen`、状态及引用处理前排除。
- 证书先判断可追溯来源的 scope。直接 evidence 优先；缺直接 evidence 时，可用 source_revision.evidence 确定其属于其他部署并排除。此回退不能提升证书核实程度。
- 无证据人工旧声明继续保留为未知；人工较新未核实字段修订继续遮蔽较旧已核实字段，避免复活旧事实。
- 本部署 conflict 继续优先阻断确认。导出快照元数据原有主体/scope 规则不变。
- 匹配批量预取 `source_revision__evidence`，避免回退检查逐证书查询。

## 本轮实际验证

命令主体（`.runtime/company-test/python/Scripts/python.exe`）：

```text
scripts/baichuan/check_backend.py portal.tests.test_baichuan_matching_scope.MatchingScopeTests.test_foreign_conflict_cannot_poison_current_verified_certificate portal.tests.test_baichuan_matching_scope.MatchingScopeTests.test_foreign_revision_ignored_before_current_field_seen
scripts/baichuan/check_backend.py portal.tests.test_baichuan_matching_scope portal.tests.test_baichuan_matching
```

第二条 **29 PASS / 9.064s / 0 skip**，包括 10 条新增及 19 条原匹配专项。runner 清理继承 PORTAL 配置、使用全新文件 SQLite 与私有存储；测试显式禁止搜索、网络和模型。覆盖：

1. 当前已核实证书 + 其他 scope 冲突，仅当前部署可确认，结果无其他部署证据 UUID/证号。
2. 只有其他部署证书时保持 unknown，无证据引用泄漏。
3. 同 scope 冲突仍为 candidate/conflict。
4. 无证据人工旧声明保留、未知不提升。
5. 其他部署字段修订不抢 `seen`；纯其他部署字段冲突无引用、未知。
6. 无证据较新人工修订仍保护当前状态。
7. 通过 revision 来源可识别其他部署证书；直接本部署 evidence 优先。
8. 证书数从 1 增为 9，匹配 SQL 查询数相同，防止回退来源 N+1。

新增 module/匹配 module/原匹配 tests 三份输入 SHA 在本轮前后保持。该结论是隔离算法/ORM 专项，不是新浏览器或真实模型验收，也没有把 29 与之前回归数量相加。

## 冻结证据

私有目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/matching-scope-review/`，保存 `before-matching.py`、red/green intent、日志和收据。

| 文件 | SHA256 |
| --- | --- |
| 修前 `baichuan_matching.py` | `5ca981f30d619e565a713188572235e0e48750022ee8e6f1b12a5d78290801d6` |
| 修后 `baichuan_matching.py` | `888ebd2ebc9920c720a5a19a7a3a81cd0e2976fff13c9eb1a72fe78d703c6be9` |
| `test_baichuan_matching_scope.py` | `b18e9d7cc77e42fa0f29e2a977781f9405d54eaf2e2b482ba85be2c574c90659` |
| 原匹配 tests | `035ff1c9b8f4a06e83706d8f4f636b5ce13c7c618704eda7f76622591d7df55e` |
| `red.log` | `f699d1c2d40c1a4a407bf09b46f75030e3ca909eb6c94c5205c43a18bfde2796` |
| `red-receipt.json` | `2d69706ae38eb8096635d62a8927d666831f820dfc4aa9fa7badde42a8e49535` |
| `green.log` | `ceb905f7a38b43d51b7060b864ae669b2599a7b1d39ffbb08b59dbb29269c105` |
| `green-receipt.json` | `c35df8de7d33b66399ff08de9a9e6b39008918107112c5b40084a9d5e4f2467a` |

本单元已完成代码与专项验证。后续统一回归、所属本地后端加载和 GM 实际断网恢复仍由根任务按各自收据核定，不在此预标通过。
