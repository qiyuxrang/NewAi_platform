# AI-T10 / AI-T12 公开研究运行单元

日期：2026-10-17（北京时间）。基线 `ef1676cd8327d693dab897c45a234ba91413884e`，本轮工作区实现。新增 `baichuan_research_runtime.py` 与 `test_baichuan_research_runtime.py`；复用已有公开搜索、DNS 固定 TLS 抓取、模型网关、租约/预算及事实服务，无新依赖。

## 隔离检查

使用 AI-T03 的显式隔离配置和解释器，从 `services/business/backend` 执行：

```text
manage.py test portal.tests.test_baichuan_assistant_models portal.tests.test_baichuan_research_runtime portal.tests.test_baichuan_research portal.tests.test_baichuan_facts --verbosity 1
```

38 tests / 29.064s / OK，system check 0 issues。覆盖模型增量迁移/回退、旧事实保护、队列恢复和下列运行路径。

最后把查询研究计数与每企业恢复点改为同事务持久化，修复预算中断前进度不可见及恢复后计数被零覆盖的问题，再执行：

```text
manage.py test portal.tests.test_baichuan_research_runtime --verbosity 1
manage.py makemigrations --check --dry-run
git diff --check
```

14 tests / 5.220s / OK；No changes detected；diff check 无错误。断点恢复计数保持不变并有断言。

1. `run_query_research` 对相关候选按预算分批研究；只将库内公开名称与固定资质/公开资料词发给搜索，测试明确断言内部招标文字、人工联系人和内部电话没有进入搜索。
2. 搜索结果仅作 URL 线索，实际正文由已有安全抓取器读取。优先读取已记录官网，即使搜索缺配置仍能尝试官网；正文失败、无搜索、模型不可用及引用错误保留具体缺口。
3. 正文及失败持久缓存，正文 24 小时、失败 10 分钟，同任务失败地址不重复读取；短暂网络最多 3 次并采用 0.1/0.2 秒退避，TLS 证书失败和永久不可访问不重试、不关闭 TLS。次数和模型/来源预算是真实持久计数。
4. 正文存于受控运行存储，内容哈希、缓存文件字节及读取范围校验；Windows 写入禁用隐式换行替换，换行和哈希有实测。定位明确 10000 字符抓取上限和 `full_text_not_confirmed`，不能声称网页全文已核实。
5. 模型只提取带逐字引文的建议；未知来源、编造引文、额外权限字段被拒绝。证书 category/grade 只由引文中 raw_category/raw_grade 及明确别名/中文数字映射导出；颁发人、持有人、范围和日期无原文就舍弃，主体保持 unknown，不自动推定证书有效或未撤销。
6. 每条事实建议有 `web_quote` 证据，保留页正文哈希、来源页证据 ID 及 quote_start/quote_end，引用与原文可对照。模型/引用不可用时可保留电话/邮箱连续原文建议，但不冒称 AI 已完成提取。
7. **独立、保守的企业联系字段核验**：既有 `corporate` 官网同 hostname 的 HTTPS 正文须同时精确出现当前企业名称与 18 位信用代码。代码保存匹配方法、名称、代码和主机依据；电话/邮箱还须由服务端正则读取带明确公司/业务/客户服务标签的字面值，招聘、证券、个人、项目联系人等上下文被排除。证据内 field_assertions 限定被核验字段及值，其他模型提取不能借主体核验自动升级。
8. 只有维护权限和事实写入开关允许时才能补空上述独立核验字段。原有非空人工值保持冲突建议；只读身份不能写事实，也不能用建议污染共享匹配。测试实际验证自动补空电话及队列 verified 字段计数；同来源只读、代码不匹配、不同主机、集团介绍页和招聘语境均未升级。
9. 不授予公司官网证书颁发机构权威或撤销核验；`authority=corporate` 不满足严格证书核验。缺证书原始依据的候选仍待核实。研究工作项、建议/合格补空与任务检查点在同一有效租约事务提交，断点/失败重试沿固定清单继续。
10. 全库执行器处理原清单内 pending（关联重试可含 failed），不缩小分母；最后一批由 record_batch 进入完成或部分终态，空清单重试也显式 partial，不会挂在 running。

## 实际公开来源探测

将 `PYTHONPATH` 明确设为 `services/business`，以已有 `fetch_public_page` 读取公开地址 `https://www.huawei.com/cn/`，仅请求公开页面，没有提交企业库、招标文件或私人信息。

本机实际结果：`ssl.SSLCertVerificationError: CERTIFICATE_VERIFY_FAILED / self-signed certificate in certificate chain`。未取得正文或哈希，未关证书校验、未以搜索摘要替代。已把该类失败纳入运行时 `source_tls_untrusted` 持久缺口与不重试测试。本条仅证明当前执行环境的 TLS 信任缺口，不能代表已成功研究该公司。

## 完成边界

- 隔离 fixtures 证明研究、缓存、建议、受限合格补空、字段报告及恢复路径；不代表真实搜索/OCR/目标部署均可用。
- 全库真实清单及研究未在本轮目标环境执行；AI-T12 的实际企业研究与 AI-T18 核账仍待真实数据源确认、备份和来源能力就绪。
- 证书严格核验需要颁发/主管机构或可验证证书的独立适配；本实现不会通过把 AI 输出标成 verified 来绕过缺口。联系人及没有可靠公开依据的字段也保持待核实。
- 后续恢复：先读任务/清单检查点、配置真实数据源标记与备份引用，验证本机 TLS/搜索可用性，再用已授权的小批真实来源核查；不能直接宣告全库资料完整。
