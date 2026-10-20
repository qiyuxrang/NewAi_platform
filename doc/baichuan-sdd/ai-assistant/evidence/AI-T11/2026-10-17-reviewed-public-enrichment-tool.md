# AI-T11 独立公开资料复核批次补录工具

日期：2026-10-17。用户要求独立补资料、使用时不自动补查；本单元只交付维护工具、后端服务和隔离验证，不改前端、常驻服务配置或共享任务状态。本单元没有真实库写入、模型或网络调用。

## 契约与实现

- 工具：`scripts/baichuan/apply_reviewed_enrichment.py`，默认 inert。真实执行必须显式提供 `--execute --batch PATH --batch-sha256 HASH`，文件 SHA256 与精确字节绑定，最大8MiB，拒绝重复JSON键和 symlink / Windows reparse 路径；保留原批文件。
- 固定格式：`scripts/baichuan/reviewed_enrichment.example.json`。只支持 website/address/email/description/phone/province/city，每批1–50家、每企业最多10来源。没有证书、信用代码、人名或人工来源字段入口。
- `review_status=reviewed_public_source / reviewer=assistant_source_review` 如实标注由助手复核公开来源，禁止冒称人工审查。`official_site_basis=user_confirmed` 仅真实用户确认的网站可用，其余为 `legal_name_publication`。该字段记录提交者的依据，不是额外人工确认流程。
- 正文必须是实际已读取的 UTF8 纯文本，最大512KiB；hash绑定该确切文本，不能冒称HTML原始字节。准确 excerpt 及 text_start/text_end 校验截取完全一致；完整在库名称必须在正文及摘录中命中，只允许空白和中英括号归一。普通字段value必须逐字出现在摘录，不准把模型总结作为description。
- website 作为来源同HTTPS origin 的首页推导，必须同host、无额外路径/query/fragment；它与普通字段的原文摘录依据不同，subject明确 `website_basis=same_https_origin`。来源HTTPS网址禁止凭据、私网/回环/保留地址、私有DNS后缀和非443端口。工具不解析DNS、不访问网页；公开页面阅读由提交批次的前序研究完成，后续任何正文获取仍须原 pinned-fetch 边界。
- 主体匹配采用 `identity_method=full_legal_name_on_public_page`，identity_verified仅表示名称与所提交页面匹配；同时强制 `legal_identity_verified=false / publication_status=verified_official_publication / source_review=assistant_source_review`。不设置发证机构/证书主体权限、不升级证书或法律身份。

CLI锁定既有 owned local SQLite、1283恢复ID集合、原工作簿指纹、原件与归档指纹和当前精确company_id/name/version。预检全批后新建在线备份（quick_check与SHA256），目录限制当前用户SID，原正文批次私有归档。仅维护子进程的 override_settings 暂时启用事实写入，退出即恢复；socket connect/create_connection/getaddrinfo也在该子进程被拒绝，模型未被调用。

后端 `portal/baichuan_reviewed_enrichment.py` 每企业短事务、锁与 fresh 维护权限、现有 propose_field/CAS/修订：空字段写入，原非空不同值追加conflict并保留原值，同值跳过字段写入。Company.source、原资质/人员、账号及旧快照无修改路径。每企业同事务追加由scope+batchhash+company确定的完成修订，绑定item内容hash；事务已提交但外部state尚未落盘时重跑读取该修订，不重复Evidence/field revision。跨scope不复用，旧expected_version不能越过版本检查。CLI分别报告批次累计结果和 applied_this_run/replayed_companies，避免重放被误认作再次写入。

备份或归档已产生但最初state尚未落盘的启动阶段中断，会保留目录并拒绝覆盖；此时尚无企业提交，需明确维护恢复该目录，不能擅自删除。若企业提交后遇后续企业版本冲突，已提交企业由数据库完成修订作为恢复点，原备份和批文件保留；相同命令复跑已提交项不重做。

## 实测

```text
company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py
  portal.tests.test_baichuan_reviewed_enrichment portal.tests.test_baichuan_facts
首次22 tests / 13.545s / OK；补公有URL数值变体与multicast限制后22 tests / 13.413s / OK。
company-test/python/Scripts/python.exe -m unittest discover -s scripts/baichuan/tests -p test_apply_reviewed_enrichment.py -v
4 tests / 0.020s / OK。
```

新增12服务测试覆盖空字段4项实际CAS写入、原电话冲突保留、同值复用、提交后崩溃重放零新增、reader/撤权/关闭开关/旧版本、禁止字段、完整名称及括号空白规则、正文hash/准确locator/字段原文/禁止摘要编造/未来时间/禁止假human标记、私网和跨网站、audit失败全事务回滚、同key改内容/跨scope、旧快照与资质人员保留。既有facts10项同轮通过。CLI4项验证默认不导入应用或读所传私有批次、显式哈希、内容大小、重复键和原文件不变。

根准备的首批 `batch-001-jinhe.json` 只读纯校验实际通过：1企业、website/address/email/phone/description5字段；文件SHA256与根提供值一致，准确摘录/完整名称/原文/时间及同源官网约束通过。采用AST提取纯函数验证，0 Django/SQL/网络，未输出正文或字段值。没有真实入库执行，完整CLI执行/备份/私有回执将由根在显式执行时另记，不把服务隔离测试冒称真实批次已经应用。

该单元不改变全库研究覆盖与字段核实计数。官网公开披露核实与证书/法律身份核实分别报告。
