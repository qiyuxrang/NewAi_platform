# AI-T15／AC15：既有网关错误与日志边界的有限隔离验收

2026-10-18 05:57:02（北京时间）完成。先搜索本轮私有receipt/intent/log，未发现以下用例已运行记录；它们不属于407百川模块。仅选现有 `portal/tests/test_model_gateway.py` 的4个精确用例，不修改原断言，不扩跑整网关套件。

| 原用例 | 实际补充观察 |
| --- | --- |
| ModelGatewayTests.test_success_logs_metadata_not_prompts_responses_or_key | 真实generate_for_use，传输边界stub成功；事务回滚前读取1条success ModelCallLog及1条AuditEvent，不含prompt、response或key环境变量标记 |
| ModelGatewayTests.test_unexpected_exception_is_redacted_and_logged | 传输边界stub抛含精确合成secret标记的RuntimeError；返回安全internal_error，回滚前1条internal_error调用日志及1条审计，无标记 |
| ProviderUrlValidationTests.test_upstream_diagnostics_preserve_classification_without_raw_detail | 普通及stream transport各6组HTTPError，12个实际GatewayError，仅保留允许的分类/诊断字段，raw detail及伪密钥不进入错误；原用例检查body关闭 |
| ProviderUrlValidationTests.test_malformed_upstream_error_codes_are_sanitized_for_both_transports | 普通及stream transport共10组畸形code/detail，固定upstream_error，10个实际错误对象无原私密detail；原用例检查body关闭 |

外置TestResult在Django测试事务回滚前额外读取持久记录，观测实际GatewayError的code、message、diagnostic；捕获root INFO及以上handler、stdout、stderr。8个**精确**合成标记逐一检查，包括synthetic-private-input/result、PORTAL_MODEL_KEY_TEST、must-not-echo-secret和上游完整私密detail/伪key/code。没有用通用“private”字样匹配测试名称或扩大为真实密钥。共23个错误对象和两个用例各2行持久记录通过检查；日志记录不持久化完整prompt/response。

## 隔离执行及原失败

现有 `check_backend.py` 硬限制百川测试标签，故未改共享runner。私有外置runner复用其显式debug/HTTPS关闭/测试secret、临时file-SQLite/storage及业务包sys.path配置，只白名单以上4个原标签；清除继承PORTAL/PG/DATABASE环境变量。外层120秒限时，子进程socket/DNS拒绝，SQLite仅允许新临时test.sqlite3，实际1个连接且路径唯一正确，禁止连接包括mode=ro在内的所属库。实际socket、DNS、禁止SQL调用尝试均0。真实网关/模型、主库、页面/前端、服务及生产/旧测试写入均0。

首个私有runner在执行任何原用例前，因覆盖已经规范化的TEST字典而缺MIRROR键，KeyError退出；原log及receipt保留。另存v2仅将初始化改为设置TEST['NAME']、保留其余默认项，原测试及业务断言未变。一次命令构造曾在PowerShell解析阶段因嵌套引号失败，没有执行Python或生成候选runner；随后使用独立准备脚本排他创建v2，不隐去该操作失败。

v2实际 **4 tests／1.312秒／OK／0skip**，含建库迁移及销毁的外层9.933秒，exit0、system check无问题。私有临时目录随进程正常清理。没有改服务或为加载测试重启后端。

```powershell
.runtime/verification/Scripts/python.exe .runtime/baichuan-ai-local/night-acceptance-20261018/gateway-error-log-boundary-0555/run-bounded-v2.py
```

该目录采用排他创建，已执行后应读取收据而非原路径重跑；将来必要复验使用全新私有目录。

## 源码保护与限度

前后共60份文件SHA保持：原407的57输入、新AC08/09五项模块，以及gateway生产/原测试文件。gateway生产SHA `3d48928236c98472d694668431f383059f8dcc0b0c3e89e4651bb69ff3386876`；原测试SHA `59a2c46fbef8e57aa608e2ea33bf91a87d19b966e2da337408904fa548dab05a`；新五项模块SHA仍为`8394f3730393761c4bd915d66fc26c3b8d11f5a94e3a53260060f68a53962423`。

本单元只证明所选应用网关代码、普通/stream错误转换和上述捕获handler范围。不是独立model-gateway服务进程的全部日志审计，也不包括代理access、SQL DEBUG、上游厂商、浏览器、所有handler或所有业务路径；不将4项视为整gateway suite或完整AC15全部放行。没有真实模型提示注入质量结论，真实Case2历史失败仍保留。

私有目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/gateway-error-log-boundary-0555/`。包含原失败、v2意图、原完整stdout/stderr/logger、每用例观察收据及60输入前后保护。

- 首次失败log SHA256：`26ed6b443e384272e9a379699257c0515776d61ddeebd2b445513c8194839d93`。
- v2完整log SHA256：`ad9233c65a9d9a8946692a1502c5aba2e810e1382961b008840fa6c40ab4dda8`。

共享checkpoint/tasks/progress未改；验收任务放行由根执行者结合其他安全子项决定。
