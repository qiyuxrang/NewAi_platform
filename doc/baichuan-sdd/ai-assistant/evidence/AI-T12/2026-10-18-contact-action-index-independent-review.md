# 官网联系研究动作索引：独立离线审阅

实际审阅：2026-10-18北京时间，精确时刻见独立收据。任务AI-T12。本单元只审核最终`validated`子目录，没有执行构建器、已有测试或资料请求。

结论：**最终派生索引在声明的离线动作合并范围内PASS，无阻断缺陷。** 它不是最新业务数据库核账，不意味着字段、身份或证书全部核实。

| 独立核对 | 实际结果 |
| --- | --- |
| 最终receipt的输出SHA及字节数 | 6/6一致 |
| 冻结input-manifest | 37/37 SHA及字节数一致 |
| 原first派生输出 | 6/6原SHA保持；旧错误未覆盖 |
| 父索引1283家 | ID与顺序、全部非field_signals属性、字段集合及父summary逐项相同 |
| 旧来源/引用 | 原source数组不变；4676旧signal定位前缀完整保留 |
| 新动作 | 49个互斥公司ID、67项逐字段动作：phone2/email44/address21 |
| 信号槽位 | 2792→2857，新增65槽位，另2项为旧槽位重新研究 |
| 维护及未知分区 | 3个冻结批次、6个apply/replay状态绑定13项；余54项未知，与67项精确互斥分区 |
| 下一步清单 | 5360个父时点空且无对应signal的槽位；保留fresh RO版本/空值重查要求 |
| URL账本 | 1939个唯一URL；状态成员readable528/discovered1552/failed96，可重叠，不能相加当唯一源数 |
| 新来源定位/归档 | 15个新event引用真实解析；18个raw/body引用实际文件SHA核对 |
| W9纠正指针 | JSON Pointer的`~1`转义正确，解析得到实际HTTPS TLS失败节点；历史W9 hash一致 |

本审阅器首次错误地把`current_empty_fields`里的credit_code纳入固定12字段恢复集合，第二次错误地要求整个JSON文档引用也必须带`#`。两次均为审阅器假设错误，原失败记录分别保留，修正独立审阅器后得到上述结果；没有修改目标子索引或放宽实际字段/来源保护。

被审生成单元的首版曾把W9引用写成不存在的顶层`#/attempted_sources`；最终validated派生件改为实际operationalFAIL补充证据中的精确`prior_attempt`指针。独立审阅确认原指针确实失败、最终指针正确，首版文件仍保持原SHA。此前第二电话12家的重复GET operationalFAIL亦保留，未计新唯一源或字段。

独立运行命令：

```powershell
.runtime/company-test/python/Scripts/python.exe -X utf8 .runtime/baichuan-ai-local/independent-enrichment-20261017/review-contact-index-independent.py
```

最终进程exit0。独立脚本拒绝SQL/DNS/socket/HTTP入口，实际0调用；未导入Django或调用模型。仅写新的审阅目录与本证据，未写主库/核心/前端/服务/共享状态。

独立私有目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/contact-index-independent-review-20261018-0537/`。

- `receipt.json` SHA256 `3249fd21b2a99a9cbfb4864f9f0f2b634a045eeaf17fc29c6d84fddb645ba49b`。
- 被审最终`validated/final-receipt.json` SHA256 `555fd6c794a3eadd61a7b0978278f82f7629cbaa9523bcaf1d3712e575a53d7b`。
- `frozen-review-inputs.json`保留输出及37个输入逐文件SHA；两次审阅器失败JSON不覆盖。

限制：13项应用仅核对已冻结维护批次及completed/apply/replay收据，未打开业务数据库重新确认当前字段；累计applied数不当作重放新增。父summary、版本与空字段是历史取样，故意未刷新。1939 URL账本只覆盖父已解析元数据、四个联系单元及指定operational补充；更广的2234 URL并集仅绑定hash并明确未合并，不能宣称全历史去重已完成。旧HTML丢失限制原样保留，本次仅查18个新增账本归档引用，未做全历史raw扫描。来源可读不等于字段满足，discovery不等于正文或失败，unknown不等于没有。
