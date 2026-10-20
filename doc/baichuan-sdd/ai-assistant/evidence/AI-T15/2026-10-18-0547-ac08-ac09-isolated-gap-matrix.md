# AI-T15：AC08/09最小隔离补证矩阵

2026-10-18 05:49:03（北京时间）完成。先核对现有匹配、研究runtime及security测试：旧测试已证明0确认候选排序、网络有限重试、研究安全和普通查询零研究，但缺少零确认/真空结果API成对断言，以及独立manifest下的延迟超时/不可读/冲突来源预算与旧快照组合。本轮只新增 `test_baichuan_acceptance_gap_matrix.py`，未改生产代码、旧测试或共享SDD状态。

## 实际5项结果

| 场景 | 实际路径与断言 |
| --- | --- |
| AC08：0确认但有候选 | 真实 `save_match_snapshot` → 现有结果API；confirmed0/candidate1，精确电子二级投标人及西安市条件原样返回、未放宽，两个条件均unknown且各有非空原因。总量/页范围正确，缺证据保持空而非编造，旧快照四字段指纹不变 |
| AC08：真空结果 | 实际空合成企业库生成快照并经API读取；total0、三种分类计数全0、结果及来源为空，仍保留原精确条件，没有伪造企业或扩大条件 |
| AC09：搜索失败及延迟超时 | 实际独立manifest → `run_one` → `process_research` → 持久工作项。搜索fixture抛不可用；fetch每次真实等待10ms再抛TimeoutError，实际3次及现有0.1/0.2秒退避。持久来源预算4（搜索1+读取3），模型0，2字段inaccessible，尝试结束但verified0。旧人工值、旧快照保持 |
| AC09：摘要有电话、正文不可读 | 搜索fixture含精确公司名/电话/邮箱线索；真实读取边界fixture抛永久ValueError，1次不重试。来源预算2、模型0、0事实建议/证书，正文/hash为空且明确不可读；2字段inaccessible，不能把摘要作为正文 |
| AC09：同主体两正文电话矛盾 | 已有合成corporate官网及可追溯联系页，各有全称、信用代码和明确公司电话；真实研究提取/证据/修订服务处理，外部模型仅确定性fixture。实际来源预算3、提取预算1；两条相反电话都存conflict并绑定各自正文断言，原非空电话/版本/全企业行和旧快照不变，没有applied或已核实字段；phone pending_review、email not_found |

后三项均检查固定1企业×2字段分母、原查询和研究共2任务、唯一旧快照及其condition_tree/results/counts/fact_cutoff_at摘要。研究结束completed、租约释放，仅表示本次有界字段结果已记录，不代表资料核实成功。全部 verified_fields/fully_verified_companies为0。

延迟超时使用受控10ms提供者替身，证明有限重试/预算/持久结果，**不是公网timeout性能实测**。两正文冲突使用完整合成原文，不是真实企业或真实模型身份核实。

## 隔离、命令和结果

使用现有解释器与 `scripts/baichuan/check_backend.py`，runner创建新的 `.runtime/baichuan-checks/tests-*/test.sqlite3` 和临时storage；移除继承PG/DATABASE环境变量。测试中SQLite连接只能指向该临时测试文件；socket连接、DNS及普通查询模型均拒绝并确认0调用。未访问所属主库/认证、HTTP、真实模型，未操作服务、迁移、前端或全局配置。

```powershell
.runtime/company-test/python/Scripts/python.exe -X utf8 scripts/baichuan/check_backend.py portal.tests.test_baichuan_acceptance_gap_matrix
```

实际由私有 `run-isolated.py` 在120秒硬超时下执行上述唯一命令：**首轮5 tests / 2.242秒 / OK / 0skip**，含创建/销毁测试库外层共11.664秒，exit0，Django system check无问题。没有红失败或为通过削减断言，没有重跑旧套件。新模块尚未并入主代理下一轮完整回归，不宣称407+5已整体通过。

407冻结输入中的57个生产/旧测试/runner文件执行前后SHA均与原收据相同；runtime SHA仍为 `227d05fc3e31ba566ac7ca1e2cd87d059f703aef4b3fd24bd283061759e614f1`，facts SHA仍为 `19efbed913a75a76e813b1991537854a16664f9d25ee108c8bcdc30c522d930c`。仅新增测试无需重载业务后端。

私有目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/acceptance-gap-matrix-0547/`，包含运行意图、原始完整log和首轮收据。输出排他创建，恢复应读收据，不覆盖或重复运行。

- 新模块SHA256：`8394f3730393761c4bd915d66fc26c3b8d11f5a94e3a53260060f68a53962423`。
- `targeted-first.log` SHA256：`289ec5f485bbbc7d1506339275ba6ee8baae361c3c18ed8cc8ec31cdbf40510a`。

本单元补充AC08结构化范围/缺口API和AC09独立失败矩阵，不替代浏览器可见解释、原生无模糊环境、真实网络/模型质量、全库逐字段终态或权威资质核验。普通文字/上传/追问/retry零研究已有证据，没有复制该测试实现；完整任务及验收放行由根执行者统一收束。
