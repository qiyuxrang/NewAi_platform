# AI-T10 企业搜索相关性与缓存门禁

2026-10-17，HEAD `ef1676cd8327d693dab897c45a234ba91413884e`，未提交工作区。由首家真实试查发现的无关结果触发，问题与对照见 [真实RSS相关性](2026-10-17-bing-company-relevance.md)，原试查和固定清单见 [AI-T11](../AI-T11/2026-10-17-original-source-pilot.md)。

## 改动

`baichuan_research_runtime.py` 增加 `SEARCH_RELEVANCE_POLICY=full_public_company_name_in_title_or_text_v1`。搜索线索必须在标题或摘要单字段中包含当前企业完整公开名称；仅归一空白、中英文括号及casefold，不通过URL、拆散拼接、近似主体或模型推断放行。此门禁只证明可继续读取的相关线索，仍不核验事实、资质、持有人或日期。

持久化received/accepted/discarded数量及策略版本。非空结果全无关保存 `web_search_irrelevant_results`；真正空结果保存 `web_search_no_hits`，不假称企业资料不存在。旧search_index没有该策略的缓存保留但不复用；其他TTL、来源及正文缓存不变，既有企业官网仍可独立读取。

## 实际检查

```text
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan_research_runtime portal.tests.test_baichuan_source_pilot
```

29项/9.673s/OK，无跳过。覆盖完整名称标题/摘要、空白/括号/英文大小写、另一公司及只在URL出现名称不放行；全无关和真正无命中分别记录原因；无关结果不触发正文或模型；旧缓存不删除但跳过、新版本缓存可复用；搜索全无关仍可读取既有官网，不升级身份。原pilot及runtime预算、来源/事实保护回归包含在29项内，不与先前32项相加。

py_compile与git diff --check通过。仅修改runtime及合成测试，没有真实重试、实际库写入或外发。原失败pilot记录保持原时刻事实，不能用本轮fixture重写成成功。运行中服务须通过owned启动器重启加载；搜索/研究开关仍保持关闭，等待企业相关性合格的来源能力。
