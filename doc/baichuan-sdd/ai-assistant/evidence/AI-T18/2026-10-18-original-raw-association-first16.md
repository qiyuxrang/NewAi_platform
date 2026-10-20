# AI-T12 / AI-T18：原档关联前16条离线核查

2026-10-18，北京时间05:54–06:02。仅处理原`stage-data-audit-20261018-0359/archive-hash-appendix.json`中`source_chains_without_direct_journal_archive_record[0:16]`，保持原顺序，没有扩大为全141条。固定父附录SHA256 `b269d7baecb09311ed4a9a69070e36a4386a80458c63b308c5491af67847e383`，其对应阶段收据SHA256 `10a69ece8c5832085cf03d6429b5a96a0e5dd7061d8b03ba0afae19379f5b13c`。

实际16条关联覆盖15个企业，逐条保存原ref、企业UUID及完整名称、原来源URL/采集时间、原body/excerpt哈希、原locator、新的原档locator、原记录rawSHA（有则保留）、实际文件SHA、解析方法与判定。结果14条resolved、1条candidate_not_resolved、1条unresolved。它们只表示来源与原档的精确关联，不表示字段、身份或证书已独立核实。

| 原序号（零基） | 主体 / 来源 | 判定与依据 |
| --- | --- | --- |
| 0 | 西安博达软件股份有限公司 | resolved；无历史rawSHA，但原fetch_f解析完整正文逐字符及SHA等于原journal，URL、主体和原路径绑定 |
| 1 | 陕西云创网络科技股份有限公司 | unresolved；原render_f只保存innerText，未保存原渲染HTML/DOM，不以同企业较早静态HTML替代 |
| 2 | 易迅通科技有限公司 | resolved；原路径+原rawSHA；原批片段精确包含于同URL完整原正文 |
| 3 | 陕西凯笙信息技术有限公司 | resolved；同上 |
| 4 | 西安乐高云智能科技有限公司 | resolved；同上 |
| 5 | 陕西淘丁数据科技有限公司 | resolved；同上 |
| 6、7 | 陕西航天泵阀科技集团有限公司，两条独立来源片段 | resolved；同一原HTML/rawSHA，分别校验完整介绍片段与页脚地址片段的精确哈希，不重复算企业 |
| 8 | 陕西烽火云集信息科技有限公司 | resolved；原路径+原rawSHA及原正文片段精确绑定 |
| 9 | 长安银行股份有限公司 | resolved；同上 |
| 10 | 西安格蒂电力有限公司 | resolved；同上 |
| 11 | 西安榴莲网络科技有限公司 | resolved；原保存DOM路径和历史rawSHA完全一致，版权片段精确来自原完整innerText；普通HTMLParser不能复现原innerText的事实另保留 |
| 12 | 中控数科(陕西)信息科技有限公司 | candidate_not_resolved；原DOM路径、URL和journal关联存在，但无历史rawSHA且解析完整正文不等于原浏览器innerText；仅记录新盘点SHA，不升级 |
| 13–15 | 陕西华山劳务开发集团有限公司、西安天和防务技术股份有限公司、西安易能电子科技有限责任公司 | resolved；三条均无历史rawSHA，但原fetch_b完整解析逐字符/SHA等于原journal，原路径、URL与主体回链一致 |

14条resolved中10条走“原路径+原记录SHA”门槛，4条走“原解析器完整正文exacthash+原URL/主体回链”门槛。后4条的新计算rawactualSHA是本次盘点指纹，明确不是历史记录hash。所有片段均以连续原字符及精确bodyhash校验，未使用近似字符串、文件名相似、同企业归属或空白折叠来凑关联。

解析仅以AST读取原`fetch_f.py`、`fetch_b.py`、`fetch_i.py`中的`Text`类，配合Python标准库`html.parser.HTMLParser`离线处理现存HTML，复现原字符解码、换行、逐行strip与空行处理；算法完整说明、Python精确版本及三份实现SHA保存在`associations-final.json`。未执行原下载器或浏览器、未引入第三方解析依赖，没有采用新的第三方代码。保存DOM与原HTTP响应字节的区别保持明确。

31份初始输入及额外1份`research-l.json`主体回链文件均重新计算SHA，存在原stage冻结副本的逐字节相等；主库完全未打开。SQL/socket/DNS拒绝自检各通过，实际外部尝试各0。0HTTP/模型/主库写入/服务/前端/core/test改动。首次私有读文件白名单漏掉固定cohort所列的维护批档案，触发assert后修复为仅允许这些精确路径，原失败收据保留，没有放开整个目录或改原档。

中鼎原缺失`i-4-official.html`仍为**1份HTML、2处引用**，本次再次确认文件缺失；不在本16条内，未重新下载替代。原父183已映射/141未直接映射计数及原失败记录均未回写；剩余125条未进入本次单元，固定16内另有2条未解决。不能据此宣布全部324条来源已关联。

私有目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/raw-association-first16-20261018-0554/`。`associations-final.json` SHA256 `19521b16520e7b00669638c27b86e2de09c5fa757d546bb432ac27953b8b0674`；原31输入manifest SHA256 `c812616c7192a912344bdd9ed1df05a94b69d8a2366eb8f3118a0c026ae196c1`；`final-receipt.json` SHA256 `8c58f1a590086f0d654033adcfcedec7a2dffca69a8e2a0e447a745bd9e95f57`。同目录额外保存全32输入清单、完整输出清单与最终冻结绑定，供根代理只读审查，不触发维护写入。
