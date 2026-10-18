# 新增13字段独立来源链与626组合证明

任务：AI-T12 / AI-T18交付准备。实际审计通过时间为2026-10-18 06:42:02（北京时间）；目录0655仅为工作单元标识。正式AI-T18最终验收仍未开始，全库补全未完成。

本单元使用根执行者在06:38:35通过SQLite在线备份取得的固定90批/626字段快照，只读连接该快照、旧86批/613字段快照和新增4批的维护前备份。未连接当前业务库，未执行HTTP、模型、业务写入、前端改动、服务操作或共享进度文件改动。

## 本轮独立核对

- 新增4批共13字段、6家企业：地址5、电话2、邮箱2、省份2、城市1、官网1。
- 逐项核对原批次和归档SHA、维护收据、实际apply/replay结果、版本基线、确定性批次标记、字段修订、持久证据及对应成功审计事件。4份维护前备份均实际重算SHA并以只读方式检查原空值，回放新增均为0。
- 对6个不同原页面，核对原收据中的URL、主体、读取时间、原始HTML SHA和完整正文SHA；只从原抓取脚本提取原Text类，按原响应charset规则重新解析，完整字符与原正文一致。企业完整名称、字段字面值及原文locator严格对应；两份多企业页面的电话/邮箱限于该企业完整段落，排除其他企业和平台客服电话。
- 12字段来自企业目录，1官网字段来自企业自身首页。这些是公开披露资料，不表示独立工商、电话接通、证书发证或有效性核实。
- 新13条与旧613条企业/字段对互不重叠；旧86快照至新90快照的企业业务字段变化恰为新增13条，原非空值保持。6家企业版本增量等于实际字段修订数，其余企业版本、更新时间及维护者保持。
- 企业资质1460条、企业人员表及证书1622条，旧86与新90冻结快照的全部行保持相同。此处为保存性核账，不能据此声称证书已经核实。

## 组合证明的边界

旧613条沿用已固定的86批来源链证明，本轮没有独立重跑其全部原文→证据→修订关联。已独立检查旧证明257个冻结输入的SHA、613个企业字段当前值，以及各自证据和修订的完整行在两份快照中保持一致。

旧613与新13合并得到90批、288家、626个唯一原空字段，并与根062500保护收据的完整企业/字段集合相等。该结果固定于90/626快照，不代表后续实库状态、当前全部来源原档覆盖或全库资料完整度。旧原141关联核账和actor113复核均未重跑。

## 保留的失败与状态解释

首轮audit.py错误预期applied字段修订的verification_status为unverified，因此在首地址字段停止；脚本及first-failure.json原样保留。实际既有propose_field把通过公开证据校验的字段修订记为verified，而批次标记为unverified。新audit-v2.py严格核对这一实际状态及evidence.access_status=verified、公开披露分类、legal_identity_verified=false；并未放宽为任意状态，也未把内部状态解释成工商或联系电话的独立核实。第二版首轮执行通过。

根第三次电话批最初复制了错误GET-11文件名，维护前停止的failure.json和first-review-script.py一并纳入新完整输入清单；实际采用GET-04的后续维护收据。审计前一次PowerShell下rg通配路径查询报错123，随后精确读取成功，未绕过审计检查。

## 复核入口

- 私有目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/field-chain-new13-combined626-20261018-0655/`。
- 实际检查程序：`audit-v2.py`；逐字段结果：`attempt2/new13-field-chains.json`；四批标记/事件：`attempt2/four-batch-proof.json`；旧613保存性：`attempt2/old613-preservation-only.json`；企业差量与保护表：`attempt2/company-delta-and-protected.json`。
- 来源原件/解析：`attempt2/source6-raw-proof.json`；输入：`attempt2/input-manifest.json`；限定范围的结果：`attempt2/receipt.json`。
- 新完整输入/输出指纹、顺序核账和封存结果分别见`complete-input-manifest.json`、`output-manifest.json`、`accounting-sequence-check.json`、`freeze-complete.json`。这些是本单元新文件，不回写旧证明或旧清单。
