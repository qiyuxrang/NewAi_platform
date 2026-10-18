# AI-T05 / AI-T12 / AI-T15：公开证书观察入口独立审阅

2026-10-18，审阅范围为 AI-D24 的未核实公开观察维护入口、离线 CLI、独立测试及其匹配衔接。此审阅未运行真实维护批次、未访问真实业务数据库、未联网/调用模型、未改前端/服务/共享 SDD。审阅者仅修复另行授权的匹配 scope 边界，见[独立红绿证据](2026-10-18-matching-source-scope-isolation.md)。

## 发现与处理

1. 早版 CLI 只分别核对 raw/body/receipt 哈希，不能证明正文来自原始响应。已向实现者和根任务报告；实现者增加严格 UTF8 raw==body、同目录和文件名绑定。独立临时文件正向对照通过；保留 raw、篡改正文及同步回执 body 哈希的反例被拒绝。早版问题为静态发现，未把修后反例通过冒充早版动态失败复现。
2. 早版未知判定测试使用旧条件 schema，且将 verdict 与大写 `SATISFIED` 比较可能假通过；已报告并改为合法 schema，明确断言 unknown/candidate。未降低业务断言。
3. 早版同号比较遗漏原始公开 getDate 等变化；已按共同已知值的实际矛盾比较完整公开字段。新信息缺失、不同原始等级同义写法不自动变成冲突。
4. 根任务确认同号实质矛盾不能被原已核实证书优先命中掩盖。当前实现新证书 conflict、verified_at 为空，修订 unverified/public_conflict；匹配器同 scope conflict 优先，旧证书不覆盖。新增针对旧 verified 同号、来源/到期日期不同的实质断言。
5. 另发现其他部署 scope 冲突证书/字段修订污染当前匹配；原代码两个 ORM 反例实际失败，窄修后新旧匹配专项 29 PASS。该修复已单独保存证据，不计入纯审查计数。

## 当前代码边界

- 活动身份、密码状态、读/写授权及本 scope 都重新检查；事实写入与公开观察写入两开关默认关闭，CLI 只在受限维护进程覆盖。
- 仅固定 HTTPS ITSS JSON 来源、完整同名主体、实际正文/摘要一致、正文哈希、准确范围定位和逐字段绑定可以入观察。任意 model 字段、摘要状态或未知来源类型被拒绝。
- 公布的获证日、发证标签、评估机构及“有效”字面不能生成 valid_from/issuer/standard/scope/撤销已清状态；通用要求没有猜造数字等级。
- 普通观察 unverified；真实矛盾单独 conflict，均 verified_at 为空。原声明、旧修订/证据、旧快照和人工值不覆盖。
- UUID5 绑定完整 scope/company/record/source。回放核对证书属性、Evidence 完整元数据、Revision 公司/字段/对象/证据及原声明；正常重放不增加版本。
- 同号冲突只比较本 scope 或无法证明其他 scope 的旧人工声明。直接证书 evidence 优先；其他 scope 来源不进入本 scope 比较。无证据旧声明保持保守保护。
- CLI 全批 provenance 校验、原表 hash/1283 ID/精确名称、本机 owned SQLite 和默认关闭状态校验；维护锁内 validate_only 全批预检、在线备份、逐企业事务/CAS/权限重查，持久恢复点。中断可重放，同一内容不会重复追加。
- CLI 保存并比较旧企业字段、原资质/人员/证书/证据/修订/快照/账号；仅允许版本、updated_at/updated_by 的维护更新。源批文件改变或模型计数增加会保留失败并停止。

## 本审阅者实际独立检查

解释器 `.runtime/company-test/python/Scripts/python.exe`，私有脚本位于 `.runtime/baichuan-ai-local/night-acceptance-20261018/`。默认运行均 inert；以下实际运行只访问合成内存对象或临时合成文件：

```text
review-public-certificate-pure.py --run-pure
review-public-certificate-provenance.py --probe
```

纯 validator **12 PASS**：公开来源不推核实字段、通用等级/缺日期保留未知、无效字面不推 clear、相似域名/凭据 URL/query 拒绝、任意核实字段/其他公司/伪字段断言/错误 hash/定位/重复 JSON 键拒绝。SQL/socket/DNS 均拒绝，实际调用为 0。最初准备器测试 secret 长度不足导致初始化失败，修正私有合成 secret 后执行；该初始化未触及数据库或任何业务路径，不计业务失败。

provenance **2 PASS**：正确原始字节/正文/回执通过；原始字节未改而改正文及回执 body hash 被拒绝。SQL/网络/模型 0。脚本通过相应守卫，没有真实企业数据。

| 文件 | SHA256 |
| --- | --- |
| `review-public-certificate-pure.py` | `05a71a26b6c1299aeadcb5ed69d80ed2d2dc6e10dcdb987022b091b653531056` |
| `review-public-certificate-pure/receipt.json` | `49b2a880d2a5fa6ad5b0203dd5ecc9464091cfaee68c95711b7cfa3fe1dd4417` |
| `review-public-certificate-provenance.py` | `4532f40743b434e6ce4d61146772fe761e6c6e0a0318df4f2c3f6032f3bb956d` |
| `review-public-certificate-provenance/receipt.json` | `9c67203b57d809f8ac814ae265f1d53d90a3e07ae825e205f8252d2a748e26ec` |

上述独立检查在实现收口期间执行，收据保留其实际源代码 SHA（facts `12aa6548…`、CLI `5ab3d169…`），不能冒称测试了后续所有代码变更。最终只读审阅的 facts `19efbed913a75a76e813b1991537854a16664f9d25ee108c8bcdc30c522d930c`、CLI `040cb88ad7f2d2533fd2d20e22d0956ba34b28a4ae5912d04aec0444f19ad6da` 已由实现者冻结；其专项/统一回归收据由实现者及根任务另外绑定。

实现者最终补充冲突观察精确回放零增量、Evidence/Revision 篡改拒绝，报告 **21 PASS / 10.287s**；本审阅者没有重跑这 21 项，只读核对了新增断言及最终测试 SHA `027425a8f187a9d3e7a757205adad1ed696c3261ea1082930b6cd527e0370984`。损坏模拟使用明确隔离测试库 SQL，因为 append-only ORM 正常拒绝更新；这是负向夹具，未修改真实库。历史失败日志由实现者保留，不能用本报告覆盖。

## 限度

本审阅没有执行 CLI 真实库写入、崩溃恢复或真实重放；不能用静态审阅替代这几项实际门禁。实现者报告的 7 批 162 条纯来源预检收据仅只读核对，未由本审阅者重跑：`qualification-publication-sandbox/actual-162-offline-preflight-receipt.json` SHA `512e2f7ff839703293625694d1b7ea777d2d0014c97908d218633f7cf05c9cdc`。原始响应及回执证明已保留的本机采集链条，不是第三方数字签名或证书法律真实性核验；这些观察不得升级为 verified。

当前未发现仍需阻断的来源/权限/覆盖缺陷；仍须根任务完成最终统一回归、实际后端加载及真实维护保护核账。本审阅不改变验收主行、任务状态或全库核实数量。
