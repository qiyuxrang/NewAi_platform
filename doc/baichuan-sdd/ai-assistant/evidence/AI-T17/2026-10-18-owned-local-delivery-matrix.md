# AI-T17：所属本地两角色验收矩阵与部署清单

2026-10-18。本单元只读19份已有JSON收据及代码/前端文件指纹，形成矩阵；**0新HTTP、模型、SQL连接、服务操作**。下述PASS均为引用收据的实际范围，不是本次重跑。frontend冻结不变，共享tasks/checkpoint不修改。实际两角色为product、general_manager，在各自授权的百川入口验证，不外推其余总经理业务页面。

**01:39 GM增量更新：** 上段为初版汇编行为。随后独立GM真实原页面单元实际新增1次上传/1query/1模型（日志21），前后企业与旧记录保护通过；两份验收器FAIL均保留。追加只读补审没有重发或调用模型。GM表格逐行引用、queued时关闭/原列表操作/后台完成和4.2ms反馈按分项补证，原context未保存native storage，**GM本次刷新自动恢复仍NOT_RUN**。见 [GM实际分项](../AI-T13/2026-10-18-gm-table-inflight-partial.md) 与 [准确来源及核账](../AI-T15/2026-10-18-gm-table-source-audit.md)。

**01:52 独立GM纯文字增量：** 新会话唯一原UI查询实际PASS，Model22；裸二级电子投标人/CCRC制造商均保持exact、ITSS仅优先。202后先保存真实native owner助手存储，queued关闭→原列表→后台完成→真正刷新恢复同cid/jid/sid，4ms反馈。该新文字单元补齐本角色原生刷新及文字默认关系，旧表格原context刷新NOT_RUN和原FAIL仍保留。见 [新文字实际过程](../AI-T13/2026-10-18-gm-text-default-native-refresh.md) 与 [独立核账](../AI-T15/2026-10-18-gm-text-default-source-audit.md)。

**02:10 独立GM新文件增量：** 唯一原UI三段DOCX上传/query/Model23实际PASS，电子二级及以上/投标人段1、CCRC裸二级精确/制造商段2、ITSS二级仅优先段3各有自身引用；202先存native key/cid，真实queued关闭→列表→后台完成→原page.reload恢复同cid/jid/sid后审语义，3.5ms反馈。新文件干净全链路与默认/范围实际通过，旧表格FAIL及其原context刷新NOT_RUN仍保留，详见 [新文件实际核账](../AI-T15/2026-10-18-gm-file-default-range-native.md)。

**02:48 GM两PDF增量：** 当前版本原UI新双页文字PDF、旋转扫描各一次上传/query/model实际PASS（24、25）；页级/自身OCR来源、制造商及人员未知、needs_review保守结果通过。两新会话原生202先存储→真实queued收起→列表→后台完成→原page.reload恢复，反馈4.2/3.4ms，全部22旧快照/企业/163hash保持。详见 [实际语义核账](../AI-T15/2026-10-18-gm-pdf-scan-native.md)。高置信度旋转扫描不冒充物理低置信度，旧表格原context刷新NOT_RUN仍保留。

## 已加载版本与环境

| 项目 | 可核查状态 |
| --- | --- |
| 目标 | 本任务owned本地`127.0.0.1:13180`，库`.runtime/baichuan-ai-local/portal.sqlite3`，1283家；`dataset_kind=isolation/local_source_only`。不是远程生产或历史已补全原库 |
| 数据来源 | 用户原Excel本轮恢复，SHA256 `220ec53ebe6a87263978f297891107700070d07588a4532b62ba884d64f68f07`；历史官网研究/人工维护原数据库尚未找到，不能称其已恢复 |
| 代码基线 | HEAD `ef1676cd8327d693dab897c45a234ba91413884e`加本轮未提交工作区。不是正式release tag；用逐文件SHA证明实际加载内容 |
| portal加载 | `2026-10-18T00:55:50.313463+08:00`，prepared=loaded；最终321项后端回归PASS/170.276s/0skip，来源门禁109项为重叠专项，不相加 |
| worker恢复 | `2026-10-18T01:08:38.709707+08:00`收据完成，PID12540。portal27260、frontend21632、gateway23540、model-gateway16912四个完整identity保持 |
| 源码指纹 | final-restart加载、worker恢复及本次磁盘28文件SHA映射完全相同；该排序映射整体SHA256 `951d672c8284eeb11c60efc4514eac22387cda93a37e0000200dad817fea3318` |
| 配置/密钥 | 既有模型/解析/导出链路已实测。全局search/research/fact-write保持关闭；用户查询不会自动研究，独立维护批次另行授权执行。密钥、password、token、完整env只留私有配置，本单元未读取或复制其原值 |
| 前端 | 163个冻结文件SHA相同，frontend PID21632；不构建、不修改、不重启前端 |
| 健康 | 最近worker恢复收据4端点200、5服务owned；本次仅读收据与processes.json一致，**没有重新请求健康或向OS重查进程** |
| 备份/迁移 | 实际库SQLite在线backup副本quick_check=ok；副本66已应用迁移/0pending。未在本单元连接live DB或运行migrate。新功能关闭/编辑保护是在副本演练，实际worker暂停是另一单元，二者不冒充完整live回退 |

## 角色验收矩阵

PASS表示本列确有真实证据；`NOT_RUN`保留缺口。隔离tests验证共享实现不等于另一个角色已做相同真实场景。

| 场景 | product | general_manager | 范围与依据 |
| --- | --- | --- | --- |
| 白话：电子与智能化精确二级、字段名称/电话 | PASS真实API | PASS真实API | [6查询](../AI-T15/2026-10-17-night-real-query-files.md)，各1模型；精确等级/投标人，固定1283候选/0确认 |
| 连续追问：保留硬条件、ITSS二级仅评分 | PASS真实API | PASS真实API | 同一会话修订2、原快照保留，不把should变must |
| 原合成DOCX：仅附件上传、解析、硬软/主体拆分 | 基础流程PASS；旧等级错误保留 | 基础流程PASS；旧等级错误保留 | 原CCRC二级曾被扩大为至少二级，不能将该旧文件语义整项PASS |
| D23修复后DOCX：默认精确/明确及以上自身来源 | PASS两份新文件 | **PASS新三段DOCX：CCRC裸默认精确、电子明确及以上、自身段引用** | [产品两文件](../AI-T15/2026-10-18-real-grade-relation-docx.md)及[GM新文件](../AI-T15/2026-10-18-gm-file-default-range-native.md)；不把未核实或等级关系判满足 |
| 新两页文字PDF：页定位、主体及硬软 | PASS真实 | **PASS当前版本原UI新会话** | [原产品PDF](../AI-T09/2026-10-18-real-pdf-table-ocr-worker.md)与[GM实际PDF](../AI-T15/2026-10-18-gm-pdf-scan-native.md)，个人CISP明确未覆盖，不能归投标人；逐项自身页引用 |
| 新表格DOCX：硬谓词自己的表格行来源 | PASS修复后唯一复验 | **真实结果逐行核对PASS；原验收器总体FAIL保留** | GM电子b4/行2、CCRC制造商exact2 b6/行4、ITSS should b5/行3并含合法本轮文字引用，个人CISP未覆盖；见GM准确来源核账 |
| 旋转扫描PDF进入真实OCR+模型+worker | PASS/needs_review | **PASS当前版本原UI新会话/needs_review** | [GM实际扫描](../AI-T15/2026-10-18-gm-pdf-scan-native.md)保留自身OCR块/page/bbox及人工核对；两角色该样本置信度高，不能冒充物理低置信度验证。低置信度降为候选另有隔离tests |
| 真实XLSX生成/授权下载 | PASS两份 | PASS两份 | 共4份独立产物：默认确认0、显式候选10；三表、来源、字段与快照核对，非公式 |
| 原浏览器按钮GET上述既有XLSX | PASS两份 | PASS两份 | [浏览器恢复](../AI-T13/2026-10-17-night-readonly-recovery.md)，共4次实际下载，与原文件SHA匹配；不是另4个新导出任务 |
| 原列表/详情/来源/精确与组合过滤 | PASS真实 | PASS真实 | [源表页面](../AI-T13/2026-10-17-local-ui.md)：1283、电子精确二级346、同类OR411、跨类AND66；原声明过滤不代表核实 |
| 固定候选列表→详情→原筛选返回 | PASS真实 | PASS真实 | 同上及浏览器恢复；已完成会话刷新、条件版本与准确snapshot ID保持 |
| 默认收起/覆盖/1440、1920、390/键盘/IME | PASS真实 | PASS真实 | 夜间6上下文及输入法追加检查；面板外原搜索可操作，0新增业务查询 |
| 当前库真实在途收起、后台继续、刷新恢复 | PASS 1次原UI查询 | **PASS新纯文字、DOCX及两PDF原生存储+实际刷新；旧表格刷新NOT_RUN保留** | 新GM文字/DOCX/两PDF会话分别实际queued收起→列表→后台完成→page.reload同cid/jid/sid；未注入cid |
| 原生真实offline刷新→online原页刷新恢复 | **PASS本新v3会话；前两验收器FAIL保留** | **NOT_RUN** | [离线重连实测](../AI-T13/2026-10-18-040619-native-offline-reconnect.md)：原context/原native key与cid/jid/sid恢复，错误页存储不可读如实记unavailable；不声称离线外壳可用 |
| 1秒操作反馈实测 | PASS，原UI **4ms** | **PASS，文字PDF4.2ms/扫描3.4ms；既有DOCX3.5ms/纯文字4ms/旧表格4.2ms保留** | 各GM原UI独立submit计时；既有四个文字API首结果上界均<5秒，见[性能核账](../AI-T16/2026-10-18-performance-target-reconciliation.md) |
| 双向他人会话/任务/快照/下载拒绝 | PASS真实404 | PASS真实404 | 6查询单元8次双向越权GET；执行中撤权、跨部署及恶意输入有隔离专项，不冒称本轮真实账号撤权 |
| 独立全库研究的网页角色任务 | **NOT_RUN** | **NOT_RUN** | 维护批次由受控CLI/维护身份执行，见下节；不是两工作台各发起研究任务 |
| 新功能关闭后旧精确列表 | PASS在线备份副本 | PASS在线备份副本 | [关开关副本](2026-10-18-flagoff-backup-rehearsal.md)：1283/精确346；product副本人工保存200与旧版本409，GM仅后续读取，不外推GM编辑 |
| 实际worker暂停时旧列表/恢复 | PASS真实200/1283 | PASS真实200/1283 | [worker演练](2026-10-18-owned-worker-pause-recovery.md)：只重启worker，其他4identity/旧行/163hash保持，模型20→20 |
| 无背景模糊环境 | **NOT_RUN** | **NOT_RUN** | [真实缺口调查](../AI-T13/2026-10-18-blur-environment-investigation.md)：Edge禁用参数未生效，不改DOM/CSS伪造支持缺失 |

## 独立维护研究与数据交付分层

受控维护路径已实际完成公开来源候选→维护复核→增量补空→冲突保留→备份/摘要核对→重放新增0。H1实际10家16字段、W12reviewed1家2字段的当时根取样为累计154家368原空字段；官网100、电话1032、地址128、邮箱69。这是历史取样口径，保留对应原收据，不当作最新状态。这是**CLI/维护身份操作证据**，不记入上表任何网页角色研究任务PASS，也不把reviewer `assistant_source_review`称为人工核验。

新增汇编引用根 01:55:33 时点保护收据及 [S1实际审核应用](../AI-T12/2026-10-18-huitie-s1-reviewed-apply.md)：44完成批、157家376原空字段，官网100、电话1032、地址131、邮箱71；41685原业务行、15夜间尝试快照+6旧快照及163hash保护。该取样时助手新增会话14与新增认证session13是不同对象；认证session总34。此段来自根历史收据，不称本矩阵新增企业补录或独立重复覆盖核查。

所属实际库纯结构化匹配另有新 [只读性能证据](../AI-T16/2026-10-18-actual1283-readonly-matching.md)：owner2/固定1283，1连接首样本463.688ms，12热样本最近秩P95 553.167ms；全表前后摘要、模型22与163hash保持，0HTTP/模型/业务写入，不记为第二份角色UI操作或首屏绘制。

固定1283企业ID/15396字段研究清单及队列已建；1283首次公开发现尝试不等于完整研究。原1460资质均未独立逐证核验，发证机关核验0；默认0确认/候选不是功能失败，既有原字段与人工修订受保护。公开披露补空不等于工商/证书权威核实，剩余全库资料任务保持未完成。

## 尚未放行格与外部依赖

GM新PDF/扫描角色差异已由本次两原UI新会话实际补齐。新纯文字已补齐该角色文字默认和原生刷新，新三段DOCX补齐文件默认/明确范围及干净文件流程/刷新；旧GM表格原context刷新NOT_RUN/脚本FAIL仍保留，其逐行来源、在途收起、后台完成、原列表和反馈已分项核对。是否补齐剩余格由主执行者按AC18实际范围决定，不能默认为已执行。文本+附件冲突、复杂取消/进程崩溃/撤权等已有隔离证据；本矩阵不将其扩写为每角色当前UI真实操作通过。

外部/环境依赖：真实无backdrop-filter浏览器；自主独立worker中文企业搜索相关性/可用服务凭据；当前7类证书的主管/发证渠道主体、范围、日期及撤销核验；历史研究/人工维护原库定位。会话联网工具维护批次可继续，但不冒充应用搜索已开通。远程生产未授权、未执行，本地环境也不是最终远程部署证明。

旧库在线backup副本演练和真实worker暂停各有成功证据，仍没有在真实原库执行“关flags+代码切换+完整故障回退”。保守恢复必须保留增量表与后续人工值，不能restore旧整库或unapply0046冒充安全回退。

## 私有manifest与来源冻结

私有`.runtime/baichuan-ai-local/night-acceptance-20261018/worker-pause-rehearsal/local-delivery-matrix-manifest.json`含19份原收据SHA/字节数、19格机器矩阵、28个loaded/disk文件SHA及角色边界；SHA256 `db99500a7138721998e21f241324d2d442d91dfaebb13cf1cbd4678ab19fd07c`。保存于已设置当前SID私有ACL的演练目录，不含密码/token/secret原文。

本轮只读证明19份现存收据可解析、loaded=worker=disk28文件、frontend163指纹及processes注册表与最近成功收据一致；未重复健康、SQL、模型或浏览器验收。功能实现、所属本地部署子项、全库发现覆盖和字段/证书核实分别呈现，AI-T17整项状态由根代理统一决定。

GM增量后机器manifest保留初版副本 local-delivery-matrix-manifest-before-gm.json；当前仍19格、来源24份（新增5份原失败/实际结果/只读核账收据），SHA256为 53ff45a80df003fb4416bb388625b4bdd8221c383a0d611bfb8ad6e1424b8ba2。本次矩阵更新仅从收据组装，0 SQL/HTTP/model；原19份汇编收据及原哈希仍可复查。两次GM执行合计新增业务会话2（一个空失败会话）、附件1、消息2、job1、快照1、模型1，Django session实际34→34/0新增；不是一次完整GM刷新复验PASS。

新纯文字后当前机器manifest为27来源/19格，SHA256 `f0bb2705653cef0473ba1b18d9a95de43b0b0be461e28d663c0770b0b1ecec97`；上一24来源版保存在 local-delivery-matrix-manifest-before-gm-text.json。新增3份本新会话真实/后审收据，汇编本身0 SQL/HTTP/model；新真实单元另计query/model各1，会话1/消息2/job1/快照1，附件/导出0、Django session新增0。原20全库快照/163hash/业务原值保护PASS，全部历史来源仍保留。

02:01 后当前机器manifest为29来源/19角色格，另列 actual_catalog_ro_match_performance 与 root_latest_enrichment_receipt_reference，SHA256 `9da358027d8c542785562fc9f4dc703b800c892a192ea4bb82a542e0c155dcdc`。27来源版本保存在 local-delivery-matrix-manifest-before-actual-match.json，历史版本均保留。本次矩阵汇编只读 JSON 收据，0SQL/HTTP/model；实际13轮读取匹配计时另按专属T16证据，不混同汇编行为。

02:10 后当前机器manifest为33来源/19角色格，SHA256 `b9ca4d0e6165826ed7091dc4ddf6be5894eb88d0ff90f0caa25d93860ca62f26`；29来源版保存在 local-delivery-matrix-manifest-before-gm-file.json。新增文件真实/后审/只读格式失败4份收据；汇编0SQL/HTTP/model。新文件会话单独新增conv1/attach1/msg2/job1/snapshot1/model1（23），认证session34→34/新增0、21旧快照保护；只读审计首次UUID表示失败保留，统一两侧格式后RO通过，未重发查询或重写原PASS。

02:50 后当前机器manifest为40来源/19角色格，SHA256 `41a447765d5805835193b490983ec0abfa965492a1bc847ce31aabf21f6ac751`；33来源版保存在 local-delivery-matrix-manifest-before-gm-pdf-scan.json。新增两GM PDF真实/202存储/后审共7份来源，矩阵汇编0SQL/HTTP/model。两个真实会话单独新增conv2/attach2/msg4/job2/snapshot2/model2（24、25）；session34→34/新增0、22旧快照及企业/资质/人员/163hash保护PASS。旧失败和旧GM表格原context刷新NOT_RUN保持。

04:06原生离线重连后，机器manifest为48来源/20角色格，SHA256 `d1afcf68fc306160cd479f7d46940408f1e7dbd433a727ca8df5ffe0b9e7369e`；40来源历史版保存在 local-delivery-matrix-manifest-before-offline.json。新增8份为两次原失败及后审、v3实际/后审、无业务机制fixture与本次加载版本收据；本次矩阵汇编0SQL/HTTP/model。3次分别授权的原生会话各唯一query/model1（日志26/27/28），合计conv3/msg6/job3/snapshot3，0附件/导出/研究、session新增0；v1/v2原FAIL不改，只有v3新product会话实际重连恢复PASS，GM离线格仍NOT_RUN。原manifest的backend fingerprint字段保留其原取样含义，本次版本依据新增loaded source单独绑定，不把历史28文件SHA冒充最新检查。
