# AI-AC04：固定中度模糊扫描单样本实际结果

2026-10-18T02:53:36–02:53:39+08:00。按预先保存的意图，复用原公开合成扫描生成器，只固定 `GaussianBlur(radius=4)`，单页、无旋转；**仅一次真实 parser 调用**，不扫参数、不挑结果、不重试。没有业务 SQL、HTTP、模型、前端或服务操作。

实际为 `needs_review / ocr`，4 个第 1 页 bbox 块，解析耗时 2.3991s。关键“投标人须具备ITSS二级”置信度 **0.996**；“制造商ISO9001仅为优先项” **0.9227**；主体标签 0.9395、英文页标 0.9946。全部高于 0.85，仅有 `ocr_review_required`，没有 `low_ocr_confidence`。**因此物理关键低置信度子项仍未覆盖，不能标通过。**

原图为 1200×360、微软雅黑 40px，PDF 栅格页由实际 parser 渲染为 1500×450。先前建议口头使用的是渲染尺寸，本次使用原生成器实际参数，未另改图像或内容。没有 PDF 文字层，三行均为明确虚构的验收条款，无企业名录或内部资料。PNG 已实际打开检查，原始模糊图和识别输出均保留。

当前代码在真实 OCR 返回块的 `confidence < .85` 时添加 `low_ocr_confidence`；任何识别到的 OCR 块仍添加人工核对提示。本样本未触发低分分支，也没有误报完成核验。未继续使用该高分结果重复已有 worker 模拟测试，避免把高分 `needs_review` 充当物理低分接入证明。

已有证据分开保留：[原 OCR 边界](../AI-T16/2026-10-17-ocr-edges-and-resources.md)的 radius8 重模糊为 0 块／failed，证明无法识别时不补字；非空密码 AES-256 和损坏 PDF 实际被明确拒绝；[文件接入](2026-10-18-real-pdf-table-ocr-worker.md)的 worker 3 项隔离测试使用控制置信度 0.61，证明已满足结构化事实也降为 unknown、缓存不提升，属于受控输出而非物理低分。本轮不覆盖或倒改这些历史记录。

## 执行与恢复记录

实际命令：

```powershell
.runtime/company-test/python/Scripts/python.exe .runtime/baichuan-ai-local/night-acceptance-20261018/real-ocr-fixed-blur4.py --execute
```

退出 0，但业务结论为 `key_low_confidence_gap_retained`，不是该验收子项 PASS。再次执行会因固定目录已存在而拒绝，不能重复调用 parser。默认无 `--execute` 为零 SQL／HTTP／模型／parser 的 inert 模式。

私有目录 `.runtime/baichuan-ai-local/night-acceptance-20261018/ocr-fixed-blur4-20261018/` 设置当前用户 ACL，含调用前 `intent.json`、一次 `parser-attempt.json`、原 PDF／PNG、`actual-parser-output.json`、`receipt.json`。外层 SQL 连接与 Django 连接被拒绝；Django 临时配置指向未创建文件，结束确认无连接、无数据库文件。沿用真实 `run_parser` 有界子进程、环境白名单和子进程网络禁止机制；未安装依赖。

- 脚本 SHA256：`c884508d769d69e20bf03f89daa45b3393f54596c2c456c224ee673bf2ebc163`。
- PDF SHA256：`c53a91763aa72b9dca665cb7b1b6c63fea344e1b6e5e0ed4046d259482bab385`。
- PNG SHA256：`6ee70f2ddb5ad6862b462bb2d3ecd325309a4904288512f75c2feef6ff128ff5`。
- 实际 parser 输出 SHA256：`f3083905e04f79b550d27309f19329f19f3083d441165f0f213661736d621fbc`。
- 收据 SHA256：`fc225f1dc42001543b1af7abcdaea9b9a34410530489437e455f3706578865fe`。

本有界单元已结束。保留“尚未获得真实关键资质低于阈值”的准确缺口，不继续调参造低分，也不宣告 AI-AC04 整项完成。
