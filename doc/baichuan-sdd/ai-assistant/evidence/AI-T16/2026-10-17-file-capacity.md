# AI-T16 文件容量与明确失败行为实测

日期：2026-10-17（北京时间）。工作区 HEAD `ef1676cd8327d693dab897c45a234ba91413884e`，当前实施差异未提交。此证据仅覆盖 AI-AC17 长文件/扫描上限和解析失败子项，不能替代完整性能验收、资格语义理解或目标部署验收。

已先复查 AI-T02 单页文字/OCR/DOCX 能力证据，本次使用新的容量边界样本，不重复单页能力探测。不改业务代码；无企业数据库连接、模型、搜索、HTTP 调用或外部上传。

## 可复现命令与隔离

```powershell
& .runtime/company-test/python/Scripts/python.exe doc/baichuan-sdd/ai-assistant/evidence/AI-T16/probe_file_limits.py
```

脚本清除继承配置，限定环境变量白名单，将数据库路径设置为本轮临时 `unused-isolated.sqlite3`；结束断言数据库连接从未打开、文件未创建。主进程阻断 socket，现有解析子进程也自行阻断网络。样本和解析暂存目录均位于 ignored `.runtime/baichuan-AI-T16-files-*`，退出销毁，并断言暂存无残留。

实际调用现有 `portal.product_intake.run_parser`，包括真实启动隔离子进程、OCR、本地资源限制、结构校验和失败错误映射，未 mock 解析器。显式解释器 `.runtime/company-test/cloud-ocr/Scripts/python.exe`，本轮探针时限 90 秒，未修改部署设置。外层 Python 3.13.16；OCR RapidOCR 1.4.4/onnxruntime 1.30.0/pdfium2 5.13.0，沿用 AI-T02 已核查环境；没有安装新依赖。现存 PyMuPDF 仅生成虚构 PDF fixture，非新增生产依赖，其 AGPL/商业许可记录仍见 AI-T02。

## 实际结果

每类单次有界执行；以下耗时从 `run_parser` 调用至返回，包括子进程启动，不含 fixture 生成时间。不是 P95、稳定性保证或端到端响应时间。

| 明确虚构输入 | 实际输出与断言 | 秒 |
| --- | --- | ---: |
| 100 页文字 PDF，39067 字节 | `completed/native`，100 块、2592 字符，页定位完整覆盖 1–100，无警告 | 0.401 |
| 101 页文字 PDF，39456 字节 | 拒绝 `StorageError.code=page_limit`，提示“PDF 超过 100 页，请拆分后上传。”；不返回伪造正文 | 0.542 |
| 13 页扫描 PDF，10149388 字节 | `partial/ocr`，24 块/231 字符，页定位仅 1–12；每已识别页有 `ocr_review_required`、bbox；第 13 页明确 `ocr_limit`/partial，独立 `OMITTED_PAGE13_SENTINEL` 未出现在提取文本中 | 9.742 |
| DOCX 200 段，每段 1000 字符，207036 字节 | 恰好 200000 字符，`completed/native`、200 块；末段原文精确一致，定位 `word/document.xml` 段落 200 | 0.132 |
| 上例加第 201 段一个 `Z`，207070 字节 | `partial`、`truncated=true`，保留原 200000 字符/200 块；`extraction_limit` 精确定位第 201 段；未编造/夹入被省略内容 | 0.166 |
| 一个 200001 字符巨段，200470 字节 | `failed`、0 块/0 字符、`truncated=true`；`extraction_limit` 定位段落 1，另有 `no_text`；不会将空提取声称完成 | 0.169 |
| 5001 个短段落，255487 字节 | `partial`、`truncated=true`，保留前 5000 块/90000 字符；上限警告定位段落 5001 | 0.240 |
| 200000 字符 DOCX，临时覆盖 subprocess timeout=0.001 秒 | 真子进程超时，拒绝 `parse_timeout`，明确“未保存不完整结果；请拆分文件或缩小扫描图片后重试”；暂存目录清理 | 0.013 |

脚本最终返回 `summary=PASS,cases=8,database_opened=false,network_calls=0,model_calls=0,fixtures_removed=true`，退出码 0。没有发现必须修改解析业务代码的阻断问题。

注意现有契约的区别：扫描页上限输出 `status=partial` 和页级警告，但 `truncated=false`；该布尔值专指文本/块截断，调用者必须结合 status/warnings，不能只看 truncated。百川 worker 当前使用 parsed.status 并把非 completed 附件明确标为提取需核对，因此本次无需改契约。单个超大段落不截成看似完整段，采用明确 failed；用户需拆分。

## 测量版本与剩余边界

本次所用文件 Git blob hash：

- `portal/product_intake.py`：`66ac6951fbbadff0f0f72228d83ea14045fbb499`。
- `portal/source_parsers/cli.py`：`9e22e5de010c614b97f29f172a81a160b45b4a1a`。
- `core.py`：`58f0ec0a23abe4498c71922c632026b51e900bc5`。
- `office.py`：`a19f46bbd073b8cc08625d0821f823b1d7351550`。
- `visual.py`：`e44125fc79c77c62bdea94b7d92cb4e42af0c7b4`。

尚未执行：大规模 OCR 并发压测/内存 P95、真实服务器同机资源竞争、真实长招标语义提取及浏览器展示、旋转/模糊/加密的全部组合。100 页稀疏文字样本用于页数边界，不代表 100 页密集文字实际耗时。13 页扫描样本是清晰合成小页面，不能外推真实高分辨率全页扫描耗时。慢网/预算/SQLite 竞争另有模拟或独立测试，不能用本文件探针替代；此处不重复调用公网。
