# AI-T11 本地原名录固定清单与首家真实试查

日期：2026-10-17，北京时间。HEAD `ef1676cd8327d693dab897c45a234ba91413884e`，本轮未提交工作区。范围仅用户提供原表接续的本任务本地库，历史官网/人员研究数据库未恢复，远程生产及旧试运行双库不在操作范围。

## 实现及隔离检查

新增 `scripts/baichuan/research_source_pilot.py`；默认不加载私有配置、数据库或网络。显式execute核对原表SHA、接入收据、1283个实际ID集合、能力探测收据，先创建独立SQLite在线备份并quick_check。`create_manifest`新增可选budget参数，默认预算保持原行为，仍使用已有enqueue校验及幂等请求哈希。

同事务创建全库清单并直接认领租约，后台worker不能看到queued中间态。研究使用原runtime、KeepLease、来源/模型预算、事实建议服务和record_batch；默认仅首家公司全部12字段，任务210秒、子进程230秒、模型最多1次、来源最多10次。全局研究/事实写入均保持关闭，只有脚本内显式研究开关，不能自动遍历1283家。

实际执行：

```text
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan_source_pilot portal.tests.test_baichuan_research portal.tests.test_baichuan_research_runtime
```

32项/15.957s/OK，无跳过。包括真正SQLite在线备份/一致性/拒覆盖/时限清理、全部ID与12字段固定分母、单家原子结果、1/2家限额、正常runtime fixture、不可达持久化、预算失败、幂等重复零额外调用、人工值与写开关保护、预算幂等冲突。首轮暴露Windows连接未close，改为closing后复测通过；不把首轮失败算通过。无execute模式另实际运行，writes/network均0；语法和diff-check通过。

## 实际本地执行与结果

```text
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/research_source_pilot.py --execute --source-sha256 220ec53ebe6a87263978f297891107700070d07588a4532b62ba884d64f68f07 --capability-receipt .runtime/baichuan-ai-local/capability-gate.json
```

先决收据来自真实通用RSS请求及DNS固定正文GET，不是模拟成功。通用探测只证明传输/schema，不能证明企业相关性；本次试查就是该质量验证，不是批量放行。

- 新备份：私有 `research-source-220ec53ebe6a/before-pilot.sqlite3`，quick_check=ok，SHA256 `1a1767be35cfc3ed70f0ae580b2520843f2eeb04e077791fbba4c86def237318`。
- 固定清单 `3a73d8fe-9b2e-58d1-8507-7d73b835fd61`，任务 `be3333f3-fbc5-4380-bb8c-996bcad27c95`；1283家、15396字段，数据标记actual指**当前所属本地原表库**，不指历史生产库。
- 开始19:44:06.396，结束19:47:08.967，约182.57秒，终态partial/pilot_batch_limit。
- 实际消耗来源预算10：1次搜索、3个候选地址各3次有限网络尝试。正文0、模型调用0、建议0、独立核实字段0；本地ModelCallLog总数仍5。
- 12字段均inaccessible，15384字段pending，无企业ID遗漏。原Company/兼容资质/人员全部字段摘要前后一致：`724750bb86495c671d0135e271ac6d4563f788ff4a0fae815a9e4312301d093d`；未改人工值，没有写ABSENT或升级证书。
- 原覆盖函数按全部字段终态计 `researched_companies=1`，但**该值仅表示一家的访问尝试结束**。实际链接与目标企业无关，不能解释为已有效研究一家公司，更不能宣传全库补齐；有效来源覆盖和字段核实均0。

同一显式命令又运行一次：1.799秒返回replayed_without_network=true；任务、来源计数10、模型0、字段状态和企业摘要不变。终态不隐式重试、扩批或新建清单。

私有状态/完整coverage/来源在 `.runtime/baichuan-ai-local/research-source-220ec53ebe6a/{pilot-state,pilot-receipt}.json`、受控数据库和存储，Git仅存脱敏记录。原接入备份和源件保留。

## 发现的质量缺口及继续工作

RSS对该公司返回Google/Wikipedia等无关来源；实际正文均网络不可达。之后两次受限公开对照也未找到相关结果，详见 [AI-T10企业相关性](../AI-T10/2026-10-17-bing-company-relevance.md)。暂停扩批，不据HTTP200/非空结果放行。通用成功收据已标transport-only/company_research_usable=false。

下一单元给runtime增加企业全名相关性门禁与缓存策略版本，不复用旧无关线索、不删除旧证据；同时有界研究可替换的本地SearXNG路径。后台搜索/全库研究开关保持关闭。AI-T12未开始，不能把本次访问失败的原覆盖计数当作数据交付。
