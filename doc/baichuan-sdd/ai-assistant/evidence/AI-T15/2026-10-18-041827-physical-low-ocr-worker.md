# AI-T09 / AI-T15：真实低分 OCR 到隔离 worker 的保守判定

实际取样：2026-10-18 04:18:15–04:18:27（北京时间）。本单元只写私有验收文件及临时数据库；未改业务代码、测试模块、前端、服务或真实企业库，未调用真实模型或外网。不改写此前模糊扫描、八样本或真实 UI 收据。

## 输入与边界

复用已冻结的公开合成 `ocr-bounded-eight-20261018/blur5/sample.pdf`，SHA256 `2e52b22b7834519c4037c3b82b9a8f6cea011ac1148effc226e9c1eb946c8785`。真实 RapidOCR / PDF parser 再处理一次；没有替换 parser、置信度、附件解析结果或 checkpoint。该 PDF 不是实际招标材料，不含真实企业资料。

新临时 SQLite、合成账号和私有存储运行真实 `store_attachment → submit_message → claim/lease worker → run_parser → conditions → matcher → snapshot`。SQLite 连接守卫拒绝临时目录外数据库；socket/DNS 接口拒绝网络，原 parser CLI 本身也禁网。唯一模型边界使用确定性 `generate_for_use` 替身，返回实际附件 b1 引用的 ITSS 精确二级投标人条件，不能把本测试称为真实模型理解验收。

隔离企业提前具有可满足 ITSS 二级的合成已核实证据和证书；无文件的确定匹配先实际断言 confirmed=1。这样可区分“原本无任何可满足资料”与“真实低分识别阻断确认”。事实写入关闭，研究关闭。

## 实际结果及失败保留

- b1 实际文字为“合成公开验农：校标人必须具备ITSS二级证书”，关键 ITSS/二级可定位，但周围文字有错字，不能称整句准确。置信度 **0.8449 < 0.85**，第 1 页四点 bbox 原样保留。
- 附件 `needs_review`；模型替身调用 1 次、持久技术预算计数 1，搜索来源计数 0。
- job 实际 `completed`；快照 confirmed=0、candidate=1、excluded=0。证书本身逐项 verdict 为 satisfied，整体 verdict 仍为 unknown。`unresolved` 保留低置信度、OCR 人工核对和文件提取需核对三条提示；must 保留本附件 b1 精确引用。
- 合成 Company/Evidence/Certificate/FactRevision 前后完整摘要一致；真实模型调用 0、网络尝试 0、主库访问 0。

**原 runner 仍为 FAIL，不倒改。** 首次准备器在建库前因替换 TEST 字典缺少 `MIRROR` 停止，0 OCR / 0 stub；独立 v2 仅修初始化，运行真实链路后在进程审计计数断言失败：Windows `subprocess.Popen` audit 事件 command 为字符串，原观察器只识别 list，误记 parser 调用数 0。v2 的业务观测已在失败断言前落盘。一个无 SQL/OCR/模型/网络的 Python 子进程机制复核实际确认该参数类型为 str。

没有为修正计数重复 OCR 或新开任务。另一个只读脚本对冻结观测执行 **16 项断言 PASS**，包括真实分数/定位、需核对状态、逐项满足但整体未知、持久引用、预算、来源数及事实摘要保护；原 runner FAIL 和原 receipt 保持不变。直接 OS 计数未成功记录，不能把原 receipt 的 `actual_parser_calls=0` 当成实际未运行；实际调用路径未 mock 且保存了本次实际解析产物。

## 命令与收据

解释器：`.runtime/company-test/python/Scripts/python.exe`。真实执行由外层 `subprocess.run(..., timeout=180)` 托管，输出独立日志，无重试。

```text
python physical-low-ocr-worker.py                     # inert，0 SQL/HTTP/model/parser
python physical-low-ocr-worker-v2.py --execute-isolated
python physical-low-ocr-worker-readback.py             # 16 checks PASS，0 SQL/OCR/model
```

以上为实际命令主体，脚本位于 `.runtime/baichuan-ai-local/night-acceptance-20261018/`；不要在既有私有目录重复执行会创建数据的 v2。

| 冻结文件 | SHA256 |
| --- | --- |
| `physical-low-ocr-worker.py` | `d86cfb7490f81dc9f760c99255cbe97435578ef7b72f963465e92dbca9007d9d` |
| `physical-low-ocr-worker-v2.py` | `b9484ce0cba530b75f9c7e6fec97ab95d840ea7b2fb95d5c9804f33320ed551a` |
| `physical-low-ocr-worker-readback.py` | `25adfe1d9f6d62d51eaceb69367a361d4799d0334fcf76c5e20913d47ece0933` |
| `physical-low-ocr-worker-v2/observed.json` | `34dfb65818732e55d73a6023bc79aa2d65a49aabd3b5751bb415bd8dabb6147d` |
| `physical-low-ocr-worker-v2/receipt.json`（原 FAIL） | `746acc4d5888831c0dc527f3001b45e37a703692ae5c07f73aa6b0691b71f0e0` |
| `physical-low-ocr-worker-v2/semantic-readback-receipt.json` | `6feb1580edc6775596ed4f815fc695700f25692c7cb059e6d86c52b773618f84` |

只读收据另冻结本轮 worker/matcher/product_intake/parser CLI/visual 实际源文件 SHA。没有将该独立验收并入此前 360 项业务回归计数。

## 未覆盖

本单元没有真实模型、浏览器或多页 OCR 新验收；cached `needs_review` 本次未再次执行，其既有隔离回归是另一条证据，不能冒称本次实测。上述逐项满足仍 unknown 证明实际低分不自动判满足；并不要求禁止 AI 理解或必须暂停至 awaiting_input，这两项不是 AC04 的既定强制语义。AC04 的其他扫描、旋转、加密损坏、OCR 不可用边界须继续引用各自原实际证据，不能以此一份文档统括通过。
