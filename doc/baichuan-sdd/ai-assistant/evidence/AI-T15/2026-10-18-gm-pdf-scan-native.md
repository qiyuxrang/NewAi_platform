# AI-T15 / AI-T09：GM 文字 PDF、旋转扫描真实原 UI 验收

2026-10-18 02:46–02:48（北京时间），所属本地 general_manager 原 UI 各上传并提交一次已冻结的公开合成 PDF；各实际 1 次模型调用，无重试、补发、导出、联网研究或企业字段写入。根已安排静止窗口，前端源码、样式、DOM 实现及服务均未改动。

## 输入与真实结果

| 用例 | 固定文件 SHA256 | 实际结果 |
| --- | --- | --- |
| 原两页文字 PDF | `2f562a4a30c01438445fb36e6cf79d2cf2e4e63e24de6ddf25b711ab41e6f53f` | PASS；页 1 电子与智能化二级 `grade_exact`／bidder 硬要求、ITSS 二级仅 should；页 2 CCRC 二级 `grade_exact`／manufacturer 硬要求；个人 CISP 明确保留人员能力未覆盖，不归投标人。每个谓词均有自身 PDF 页引用 |
| 原旋转扫描 PDF | `bcb49a2a37db84ee03a65f8edb01c982f40c94b85d70defa54fb8ebd782fb183` | PASS；真实 OCR，保留页 1 和 bbox，ITSS 二级 bidder 硬要求自身 OCR 块引用；制造商 ISO9001 仅优先／未覆盖说明，保留人工核对 unresolved，解析状态 `needs_review` |

两份文件完全复用原 product 成功样本，没有改文件来适配模型。每例结果均为 1283 candidate／0 confirmed／0 excluded；研究状态 `not_requested`、持久 `_budget_model_calls=1`、`_budget_sources=0`、`research_policy=independent_manifest_only`。扫描件该次识别置信度并不低，**不能把 needs_review 冒充物理低置信度扫描验证**。

## 原生关闭与刷新

两例都由原页面生成 native UUID，在 POST 放行前持久化。202 后在任何语义断言前保存真实 owner 的助手 localStorage key/cid，不保存 token，也不手工注入 cid。实际状态 queued 时收起助手，原列表搜索仍可操作；后台完成后真正 `page.reload()`，默认收起，再打开恢复同 cid/jid/sid，读取原固定快照并从快照列表返回原筛选。之后才审阅语义。提交到可见反馈分别 4.2ms、3.4ms，见[恢复取证](../AI-T13/2026-10-18-gm-pdf-scan-native-recovery.md)。

## 实际增量和独立只读后审

新脚本 `.runtime/baichuan-ai-local/night-acceptance-20261018/gm-pdf-scan-native.py` SHA256 `f728dda14ad5d643bc69e84c92a8a545c3fbb4a83b467e26f9880881ce0612c5`。默认 SQL／DNS／网络拒绝下 0 调用准备通过；14 项隔离检查通过，0.339s、0 skip。真实执行使用既有 Python 3.14／headless Edge，分别指定 `--case text_pdf --expected-model-count 23 --expected-snapshot-count 22` 与 `--case rotated_scan --expected-model-count 24 --expected-snapshot-count 23`，各带 `--execute`；第一例通过且独立只读数目确认后才执行第二例。

随后以 `.runtime/company-test/python/Scripts/python.exe .runtime/baichuan-ai-local/night-acceptance-20261018/gm-pdf-scan-post-readonly.py --execute` 实际独立只读核账通过，网络被拒绝，业务 SQL 仅 `mode=ro/query_only`。新增总计 conversation 2、attachment 2、message 4、job 2、snapshot 2、ModelCallLog 2；export／research job 为 0。模型日志 23→25：24 success／4552ms／1578 输入与 445 输出 token；25 success／4089ms／1733 输入与 366 输出 token。Django session 34→34，新增 0、旧行保留。所有 22 个原快照、旧会话消息、企业／资质／人员摘要、研究计数和 163 前端文件 SHA 保持；全库快照现为 24 个。

| 用例 | 新快照 | 四字段 SHA256 |
| --- | --- | --- |
| text_pdf | `e711f9ef-55be-4efc-ae19-41e047e24499` | `89d76a4b1b627ae2cd8a5b1c07f19f9317164f96e4ba193c4e6440604ccadda2` |
| rotated_scan | `7bc97d24-86c5-46d8-8e2e-56b37bbc4de5` | `22a88c520da36a12a2f8467f2faa947d237e51d53b1acfbca1ecbb63534b0816` |

四字段固定为原 SQL 值 `condition_tree/results/counts/fact_cutoff_at`，按 `json.dumps(sort_keys=True, ensure_ascii=False, default=str)` 的 UTF-8 字节求 SHA256，结果明细各 1283 行。

私有证据目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/gm-pdf-scan-native/`。每例保留原 receipt、原生 202 存储、前后摘要、后审及两张真实页面截图。text_pdf receipt SHA256 `e33aa69e88fbfcbe41d4bc3e27018dfb885a348f105cceadcebd33095f0b5cb8`；rotated_scan receipt SHA256 `bc6ecd50f0ab397ce2d552796c9d295e3daac8122541a95ba5a948d5b0ca7c4d`；`combined-independent-readonly-audit.json` SHA256 `b7ede4bc3fd89bbde8aca1fd254ba3eaa9e9c0e5905d8caec43068055e852e2f`，记录全部新增 ID、native UUID、模型日志和断言。

本轮补齐 GM 当前版本文字 PDF／旋转扫描及这两个新会话的原生关闭恢复证据，不重写旧 GM 表格验收器 FAIL、其原 context 刷新 NOT_RUN、旧模型等级失败或原 product 表格缺引用失败。不外推物理低置信度扫描、无背景模糊浏览器、全字段资料研究或远程生产部署。
