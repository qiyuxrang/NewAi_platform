# AI-AC04：8张固定合成页的真实低置信度OCR

实际时间2026-10-18 03:59:01–03:59:23（北京时间）。仅在新私有目录生成8张合成公开资质页，调用现有真实parser各1次，未自适应调参或重试。真实应用引擎是 **RapidOCR ONNX CPU，不是Tesseract**；未安装/更换引擎。未访问主库SQL、HTTP、模型、前端或服务，也未修改本轮回归的核心/测试输入。

原blur4关键ITSS块.996、历史blur8零块的缺口保留。新预先固定计划为GaussianBlur5/6/7、blur3加7度旋转、1/4降采样、seed20261018高斯噪声σ55、同seed12%椒盐噪声、每9像素擦除2像素竖线。各1页image-only PDF，原PNG、渲染PNG、PDF、实际parser全部块及bbox/页码/score/warnings均留档；合成正文为投标人ITSS二级、制造商CCRC二级、人员CISP优先项，无真实企业或内部资料。8页渲染联系表已目视核查，模糊/断笔是有意输入缺陷。

| 固定样本 | 实际关键结果 | parser状态 |
| --- | --- | --- |
| blur5 | “合成公开验农：校标人必须具备ITSS二级证书”，confidence **.8449** | needs_review；low_ocr_confidence + ocr_review_required |
| blur6 | “人心团具务ITSS二证号”，.5925；等级文字损坏，不称准确提取二级 | needs_review；同上 |
| blur7 | 0块 | failed；image_no_text/no_text，不能冒称低置信度提取 |
| blur3/7度 | 关键块.9377/.9556/.9909 | needs_review；只有ocr_review_required |
| 低分辨率 | .9933/.9980/.9961 | needs_review；只有ocr_review_required |
| 高斯噪声 | .9635/.9917/.9908 | needs_review；只有ocr_review_required |
| 椒盐 | CCRC .9766、CISP .9909；ITSS误作1TSS不当精确类别命中 | needs_review；只有ocr_review_required |
| 断笔 | “舍成公干验纠仗：投标人、必频具备ITSS二级证书”，**.7364** | needs_review；low_ocr_confidence + ocr_review_required |

门槛直接来自 `source_parsers/visual.py`：真实块score<.85追加low_ocr_confidence，`core.Result.finish()`遇review警告返回needs_review。低分是引擎原输出，未注入fake confidence。blur5和断笔各实际保留ITSS二级证书文字，可补物理关键低分样本证据；它们仍有其他错字，不能作为经过人工纠正的条款。此单元未将任何输出送模型，没有新增worker/真实浏览器任务，不把解析器证据当作完整AI-AC04放行；低可靠内容不误判满足的worker隔离证据按既有专项独立引用。

命令（默认inert已在SQL/network拒绝守卫下检查）：

```powershell
& .runtime/company-test/python/Scripts/python.exe .runtime/baichuan-ai-local/night-acceptance-20261018/real-ocr-bounded-eight.py --execute
```

脚本SHA256 `fe7e7d2bd780760cdb70929fac681f3b15262187ee78c0e1efcb23abd244ac96`。私有 `.runtime/baichuan-ai-local/night-acceptance-20261018/ocr-bounded-eight-20261018/receipt.json` SHA `464fc452efda9448c61a8667625f35ae717fa37c37f1c93fc5707e4be522fc2b`；intent在首调用前固定全部参数/8次预算。parser子进程原网络禁止逻辑保持，主进程SQL与网络连接守卫拒绝、Django无打开连接，隔离unused SQLite文件未创建。历史原件未覆盖。
