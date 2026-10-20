# AI-T18：70维护批次的独立阶段数据核账

这是所属本地库在 **2026-10-18 03:25:05.765867+08:00** 的固定取样，不是最终AI-T18交付，也不覆盖主代理此后继续应用的批次。原51批阶段审计及更早草稿保持原样。

## 输入与隔离

使用原SQLite的 `mode=ro`、`PRAGMA query_only=ON` 连接，通过在线backup API写入全新私有副本；副本 `quick_check=ok`。业务库从未以可写模式打开。固定coverage、63份journal、70份维护state及batch、对应原冻结batch、来源正文/现存raw、历史快照和保护收据，共1097份文件，逐文件记录路径、SHA256和字节数。后续审计只使用固定副本和冻结输入，既有维护备份另以只读连接读取并重新核对文件SHA。

固定目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/stage-data-audit-20261018-032451/`。

- `sample.sqlite3` SHA256：`54f26fb0e8c5a5ce4ce84c21b53ae8069ca6ee085f592f2789675afd7115ff5e`。
- `freeze-receipt.json` SHA256：`92251d4635af226d3369109477ecb0fb3ef814f93a839d3aba59adea9c06936d`。
- `receipt.json` SHA256：`cc7100503df2bb97007279195990eccdd42ed5685eeac927141a556d7ff9caf4`。
- `archive-hash-appendix.json` SHA256：`1d449d0125cacc210fcfe5ce6bc37c249d515fb7a882b691b530bedc9dbf05ce`。

执行命令为既有Python3.13运行该目录的 `freeze.py` 和 `audit.py`。审计脚本SHA256为 `6ca01726d22cddd8839a59291441cf41bd29161b223b1dc04449d1e275b9e0ba`；代码不导入Django、模型或业务写入服务，网络socket设置拒绝守卫。0 HTTP、0模型、0主库写入、0实际批次重放、0服务或前端变更。

## 独立对账结果

**阶段核账通过：70批、248家去重企业、536个原空字段。** 这不是全库资料补齐率。

| 检查项 | 固定样本实际结果 |
| --- | --- |
| 原表主体 | 1283个ID及规范名称与固定manifest完全一致 |
| 真实原空差异 | 248家，536字段；逐公司/字段与根保护收据及修订集合完全相同 |
| 批次计数 | applied 536，conflict 12，unchanged 12；不同非空值未覆盖，同值复用 |
| 完成标记 | 70批SHA与state/batch吻合；289个company-batch UUID5标记及item SHA/计数逐项匹配 |
| 来源修订链 | 自身company、部署scope、reviewed_public_page类型、URL、正文hash、准确excerpt/locator、逐字段断言均与冻结batch相同 |
| 来源文本 | 所有入库批次正文hash重算一致，excerpt等于其准确字符区间，正文实际包含归一后的完整企业名称 |
| 基线保护 | 41685原行保留；原非空企业字段、Company.source及原1460资质完全保留；仅允许补空字段及相应版本/更新时间变更 |
| 资质核实 | 1460条新增结构化证书仍全部unverified；法律身份核实证据0、发证机构独立核实0 |
| 快照 | 24总快照；6份基线旧行完全保留，18份夜间快照与先前收据的四字段SHA逐一一致 |
| 其他保护 | ModelCallLog 25；Django session 34；163份冻结前端文件逐SHA一致 |

维护完成标记的幂等性由UUID5、batch/item SHA、修订ID和持久计数核对。审计另外读取25个不同batch的既有实际重放收据，均为applied_this_run=0；没有在本轮再次执行重放，也没有将“70批标记核对”冒称“本轮实际重放70次”。全部70份既有维护备份的文件SHA重新核对；未将这些历史备份说成审计新建的备份。

根对应保护收据为 `night-batch-preservation-20261018-032307.json`，其536字段差异另由本审计从最早维护前备份和固定副本独立重算，不是只引用根的计数。

## 字段覆盖与缺口

下表“原有保留”不表示本轮独立核实；“新增公开披露”只表示有已复核公开正文依据，不等于工商、发证或当前法律身份认证。

| 字段 | 原有保留 | 新增公开披露 | 当前非空 | 当前空缺 |
| --- | ---: | ---: | ---: | ---: |
| 官网 | 0 | 101 | 101（7.87%） | 1182 |
| 电话 | 1024 | 8 | 1032（80.44%） | 251 |
| 地址 | 0 | 218 | 218（16.99%） | 1065 |
| 邮箱 | 0 | 97 | 97（7.56%） | 1186 |
| 省份 | 1071 | 20 | 1091 | 192 |
| 城市 | 581 | 92 | 673 | 610 |
| 简介 | 1283 | 0 | 1283 | 0 |
| 统一信用代码 | 0 | 0 | 0 | 1283 |
| 联系人姓名 | 0 | 0 | 0 | 1283 |
| 联系人电话 | 0 | 0 | 0 | 1283 |

独立批次提供实际正文的企业下界为248家、去重company+URL+bodyhash组合260个；291条批次来源关联含重复使用。主发现journal原口径的148家正文数不能与248相加。未计算全部来源journal的无重复正文并集。

全1283家有公开发现尝试记录，不代表全字段研究完成。既有固定研究清单仍为1283×12=15396项，15384 pending、12 inaccessible，与基线相同；成功完成全部12项的企业0。维护补空与该旧队列口径分开呈现。

## 来源与原档限制

260个去重来源组合的批次标注为historical_unspecified 109、directory 89、government 13、industry 16、group 1、encyclopedia 10、unknown 6、corporate 16。历史未标注不能补猜为官网。第三方目录、行业披露或公司自述均不自动升级为主管机构核验；自身主体匹配也不等于独立法律身份核实。

已知 `i-4-official.html` 早先被输出前缀冲突覆盖后缺失，当前journal有两条引用，实际是同一个缺失原档。原 `archive-integrity-i.json`、保留批次正文hash和回执已冻结；没有重新下载替代原档或修造原始HTML。

本次遍历668条journal档案路径记录，332条raw引用存在且字节hash匹配，缺失raw引用2条；正文231条字节hash匹配、101条存在字节hash差异、2条没有声明正文hash。101条差异均仅通过CRLF转LF即与声明hash相同，已在独立附录同时保存原字节hash和LF归一hash；没有修改原件，也没有把归一正文hash说成raw字节hash。现存已声明hash的差异没有剩余未解释项。

141条批次来源关联在本次63份冻结journal中没有直接匹配的URL+bodyhash档案记录。入库batch本身的正文、hash、摘录、定位及证据/修订仍已逐一核对，但这不能证明原HTML全部保留。`all_raw_archives_verified=false`，全库资料仍未完成。

## 审计执行边界

第一次审计运行在末尾扫描历史重放收据时出现脚本变量重名：输入冻结字典变量被前端文件字典复用。保留 `audit-first-version.py` 和 `audit-first.log`；将变量区分后重新在同一固定副本上核账，`audit-final.log` 给出 `PASS_interim_reconciliation_not_final_delivery`。错误未涉及原库、来源资料或修订数据变更，也未覆盖旧阶段样本。

本单元不修改共享README、任务、进度、检查点或coverage，不标记AI-T18最终完成。功能与部署、资料发现覆盖、正文覆盖和字段核实程度继续分别验收。
