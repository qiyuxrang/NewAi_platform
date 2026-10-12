# 合成短链 smoke

运行：

```powershell
& .runtime/company-test/python/Scripts/python.exe scripts/test-product-short-chain.py
```

脚本清除继承的业务环境变量，在 `.runtime/short-chain-smoke/<时间与PID>` 建立隔离数据库和存储，用合成 secret、显式布尔设置及合成资料运行一个 Django 测试。无需读取私有 `.env`，不启动或停止用户服务，不调用外部模型。

模型回复采用确定性替身，包括写作、独立复核、Mermaid 图源。worker、版本绑定、持久步骤、文件生成器、Mermaid 12、Edge、Microsoft Office 16、PDF、下载与预览接口都真实执行。正文约 1109/1454 字符，仅在测试方法中覆盖长度目标为 500/600；生产默认 50000/70000 不修改，长度约束仍启用，生产图数要求仍是 15/20。

在 PPT 渲染阶段注入一次超时，断言首次保存两份报告，随后自动恢复。恢复不能增加人工尝试计数，不能再次调用模型，必须保留两份报告的 ID 和 SHA256。三份 Office 文件检查 ZIP、全部 XML、图像嵌入；报告检查目录、PAGE 字段及无 Mermaid 源码，PPT 检查图片及内嵌工作簿。下载与每一页预览逐字节核对哈希，其他用户下载须返回 404，不自动批准报告。

三份 Office 文件的 PDF 和规范预览证据由生产生成入口自动创建。测试直接读取生成记录，要求预览证据已存在；不额外补挂元数据，不替换 PDF 或页图。

成功生成 `evidence.json`、`regression.log` 和 `retained` 实物。失败保留 `failure-state.json`（如已进入 worker）及文件。页面 PNG 供后续实际视觉检查，脚本本身不宣称完成视觉审核。

本机需要 Python 的 Django、Pillow、lxml、python-pptx、PyMuPDF、pywin32，以及已安装的 Office、Node 和 Edge。当前 runner 的 Node/Edge 路径显式选用此工作站的现有运行时。尚无 Docker、已安装的 WSL 或 LibreOffice，因此结果只覆盖 Windows Office，不代表 Linux 云端渲染验收，也不代表真实项目内容或真实模型质量。

## 2026-10-12 实跑结果

最终日志 `.runtime/short-chain-smoke/20261012-234648-15196/regression.log`：**1 项真实短链测试，65.207 秒，全部通过，无跳过**。此轮已包含最终审查追加的图源输入与蓝图绑定、终止子步骤重试、图像和预览缓存完整性检查、外层报告步骤运行时哈希绑定及 Office 阶段有界自动恢复分类；前轮通过记录保留在 `20261012-233215-14964` 和 `20261012-233949-15536`。

技术正文 1109 字符，15 张真实图，Word 14 页；可研正文 1454 字符，20 张真实图，Word 17 页；PPT 5 页。全部 35 张图的哈希实际出现在 DOCX 媒体包内，报告保存的图标题与真实 DOCX 文本一致。三个文件下载哈希一致，36 页预览哈希均与生产生成 PNG 一致；Office 预览由生产代码创建，无测试补挂。

PPT 首次渲染注入 `presentation_unavailable` 且诊断原因为 `timeout`，首次 worker 进入 `QUEUED/step_retry_pending`，下一次自动恢复。两份 Word ID/哈希不变，无额外模型调用；模型总调用 39 次，分别写作 2、复核 2、图源 35。人工尝试计数保持 1，执行记录有 2 次，最终 `WAITING_REVIEW` 且错误码为空，无报告批准。

最新版 `evidence.json` 保存完整文件、页数、哈希和范围证据。页面审计证据位于前轮 `20261012-233949-15536/page-audit/published/audit.json`，对规范发布 PDF 的全部 36 页检查文本非空、无替换字符、无文字超出页面边界。前轮六张规范发布 contact sheet 已逐张查看，未见明显遮挡或图像拉伸；短样本有明显留白。此检查属于缩略页和页面几何检查，不宣称完成逐页 100% 视觉验收或业务内容审批。

`20261012-233949-15536` 复跑重新检查全部 36 页 PDF，且全部 36 页 PNG 的 RGBA 像素与 `20261012-233215-14964` 已查看页面完全相同，证据在该轮 `page-audit/published/pixel-comparison.json`。最新版复跑未修改 renderer，沿用前轮页面审计，同时再次通过全部生产预览页哈希检查。

试跑定位并推动修复了逐图步骤丢失段落 type、发布快照缺图像、PowerPoint 冻结 renderer 缺 PDF 哈希字段、渲染内容与报告保存内容不一致等问题；最终结果以以上最新版日志为准，早先失败日志保留以供追溯。
