# AI-T17 准备 / AI-AC16：关闭新功能的独立备份副本演练

执行时间：2026-10-18 00:29:36–00:29:42（Asia/Shanghai）。范围为**当前所属本地1283家原表库的在线备份副本**，不是实际服务回退、远程部署或完整AI-T17验收。前端、实际服务、业务核心代码、原库资料均未修改。

## 可重复入口与环境

新增独立脚本：[`rehearse_flagoff_backup.py`](../../../../../scripts/baichuan/rehearse_flagoff_backup.py)。使用已存在的公司隔离测试Python；不读取实际服务密钥，不安装依赖。

```powershell
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/rehearse_flagoff_backup.py --output .runtime/baichuan-ai-local/night-acceptance-20261018/flagoff-copy-final
```

输出目录必须不存在；再次执行请给新的受控`.runtime`目录，不能覆盖既有证据。实际环境：Python 3.13.16、Django 5.2.18、SQLite 3.53.1。最终执行5.7493秒，退出0。

## 实际保护与通过结果

1. 核对所属运行目录标记、本轮原Excel恢复收据和源SHA-256 `220ec53ebe6a87263978f297891107700070d07588a4532b62ba884d64f68f07`。先对新目录撤销继承并只授权当前Windows SID，再访问数据库。原连接使用SQLite URI `mode=ro`及`PRAGMA query_only=ON`，调用SQLite在线backup，未裸复制运行中数据库。
2. 原库在线备份在00:29:36.962开始、00:29:37.511结束，`quick_check=ok`；备份SHA-256 `9051d9f9532c5b324b21575bd045eed0be4d3395b6f1da26aca883b6af969551`。再从该备份在线生成工作副本，初始哈希相同。所有编辑仅指向`working.sqlite3`；保留不变的`before.sqlite3`供复核。
3. 子进程清理继承的业务数据库/模型环境，使用合成隔离密钥、独立临时storage和指定SQLite路径，连接创建信号校验只能连接工作副本。关闭assistant、research、fact_write、product_model_calls及agent开关；不启动worker/server。
4. 实测MigrationExecutor历史一致，66项已应用迁移、**待迁移0**。未执行迁移命令、unapply0046、删表或数据库恢复覆盖。
5. 使用副本中已有产品角色和总经理角色直接通过DRF APIRequestFactory及真实旧API函数访问，保留原权限判定。两角色旧列表均返回1283家；`electronic=2`四页共346家，逐ID与独立精确SQL期望集合一致，不将一级合并为二级。此为旧原声明精确筛选行为，**不代表346家资质已核实**。
6. 旧详情200；在有原资质的一个企业上，仅副本description追加明确的隔离标记，真实旧PUT保存200、版本2→3，原子项快照相同。重放旧版本PUT得到409 `version_conflict`，未覆盖随后人工值。关闭助手时新建会话503 `assistant_unavailable`，旧列表/详情/保存仍可用。
7. 在子进程内仅恢复助手开关后，再用总经理角色读旧详情，人工标记及版本3仍保留；没有恢复旧数据库快照。结束时重新处于全新功能开关关闭状态。
8. 对副本93张表、44209个原行逐主键比对行摘要：**原行删除0**；仅预定企业行的description/version/updated_at/updated_by允许变化，其他字段和所有其他企业行保持；追加1条manual事实修订及15条对应API审计。原1460条资质、1460条证书、1639条证据、3421条原修订、15396条研究项及其主键/来源均保留，其他会话、任务、快照、导出及业务表原行未改变。
9. 副本结束`quick_check=ok`、`foreign_key_check=0`，原始备份哈希未改变。原库自身8张资料保护表（企业/旧资质/人员/证书/证据/修订/研究清单/研究项）执行前后计数及完整行摘要一致。其他代理同时合法执行文件验收，原库会话/任务计数及数据库物理文件可能变化；没有将这些变化混入本脚本的原库保护断言。
10. DNS、socket出站/绑定/监听、模型执行均有拒绝守卫。出站/DNS/模型尝试0；另有1次urllib3导入时IPv6回环能力探测的bind被拦截并单独记账，无socket绑定成功、无联网。该导入探测不冒充业务模型或检索成功。

## 私有收据

目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/flagoff-copy-final/`，包含只读原始在线备份、编辑工作副本、子进程日志及被拒本机探测堆栈；不提交企业资料或密钥。

| 收据 | SHA-256 |
| --- | --- |
| `parent-receipt.json` | `2c55af36e2e6a4d83f5f32a01822d2132d474fae00b4699fd397d2cbbcb5e3a3` |
| `copy-receipt.json` | `2ddd38dc635947b583f0db8754b1d94a64a3c0fe3a7816d49ee88dd85bb9032f` |

失败记录保留：r1目录在ACL阶段因数字SID未加icacls所需`*`前缀失败，尚未备份数据库；修复仅新脚本。r2/r3在全部旧API/保存/逐行保护执行后，因验收器把被拒的urllib3本机bind探测误算为出站而最终失败；r3保留定位堆栈。最终脚本将其独立记录，仍拒绝bind，未放宽网络守卫。未删除或改写这些失败副本/收据。

## 回退前提与尚未覆盖

保守回退采用**显式停止新worker + 关闭新功能开关 + 保留增量表和后续人工更新**。当前`run_one/claim_job`并无助手开关总停机门禁，故**单纯flag-off不能当作worker已停止**。本演练未调用worker，全部既有任务逐行保持；真实回退必须按所属进程清单停止/确认worker，不能借恢复旧整库备份抹去后续维护。本次未执行实际停止/重启。

这是AI-AC16的后端、备份、旧编辑及版本保护证据。页面交互、实际目标部署切换、PostgreSQL持续并发及完整AI-AC18不在本单元。此前T03隔离迁移/回填证据仍独立存在，本次只验证当前实际本地库副本已无待迁移；没有伪称重复做过迁移。历史已研究/人工维护原库仍未找到；全库字段和发证机构核实状态不因本次演练提升。
