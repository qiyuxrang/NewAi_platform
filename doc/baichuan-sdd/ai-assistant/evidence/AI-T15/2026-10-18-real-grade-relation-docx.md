# AI-D23 / AI-T09 / AI-T15：真实文件默认精确及明确等级关系

2026-10-18 00:16:44–00:16:59（北京时间），**PASS**。根代理确认00:15:38仅后端重载且加载指纹一致后，执行 [已准备的关系专项](2026-10-18-grade-relation-source-guard.md)；本单元不改代码、前端、服务或企业资料。

现有 product 本地身份通过真实鉴权、上传、持久任务、真实模型、匹配与结果API，执行两个独立、预写固定提交ID的合成DOCX：

| 文件实际原文 | 实际提取 | 验证 |
| --- | --- | --- |
| 设备制造商必须提供CCRC二级证书 | manufacturer / ccrc / value=2 / grade_exact | 默认精确，通过 |
| 设备制造商必须提供CCRC二级及以上证书 | manufacturer / ccrc / value=2 / grade_at_least | 谓词精确引用本附件b3，门禁validated_keys=1，通过 |

两份文件另含“投标人必须具备电子与智能化工程专业承包精确二级”，均保留 bidder / electronic / grade_exact / value=2。均无should、无unresolved，日期为实际2026-10-18查询日。附件解析completed，任务completed；两个固定快照均confirmed0、candidate1283、excluded0，research_status=not_requested。未知原表资质仍保持候选，没有因明确等级关系或非空资料误判满足。

实际模型调用 **2次、均success**，ModelCallLog ID14、15；每任务预算计数1、sources0，无重试或重复提交。输入2271、输出629 tokens，模型用时合计8945ms；本单元没有另加人工用量硬上限，也没有为诊断发健康调用。模型输入为公开合成条款，没有企业名册、联系方式或内部文件。

保护核账：Company、CompanyQualification、CompanyPerson全表有序摘要相同；验收前所有会话、消息和旧快照摘要相同；Evidence/FactRevision/ResearchManifest/ResearchItem/research jobs计数相同。完成后追加只读复核两个新快照与其首次保存摘要相同；前端冻结163文件hash相同。原失败收据SHA仍为 `336cb1bed84f0fd9235fb8b6dce22c999af838df725a6978d64018886af4bd56`，未覆盖历史grade_at_least错误或改写旧快照。

真实命令（已执行，退出0）：

```powershell
py -3.14 .runtime/baichuan-ai-local/night-acceptance-20261017/real-grade-relations.py --execute
```

私有夜间目录：

- `grade-relations-execute-001.log`：`passed / cases=2 / model_calls_executed=2`。
- `grade-relations-20261018/receipt.json`：SHA256 `bf3b3d71e6d0cc893580d82174c6cbef903e7e8237dac50a2987ef2f5ca3555f`；提交意图、原文件、任务/快照ID、实际条件、调用前后账目。
- `grade-relations-20261018/post-readonly-receipt.json`：两个新快照保护、163前端hash及原失败收据的只读复核。

默认任务 `6732a4cc-aaac-46bb-977a-9fcc4e6c5c82`，快照 `2f5a0e81-07a8-4f9c-899a-e4ae3f2c2a6f`；明确关系任务 `cc944f3d-42c1-4bf6-95e0-1ad681582bae`，快照 `7945d2d4-5696-4047-9e57-6c22387b1a05`。当前无失败/待重试任务；原脚本拒绝不确定提交重发，不需重新运行。

这是本地真实DOCX等级关系单元，不代替PDF页码、表格、OCR、浏览器、远程部署或全库证书核实。共享任务状态交根代理同步。
