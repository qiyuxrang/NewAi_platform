# AI-T02 能力调查与隔离实测

日期：2026-10-17（北京时间）。工作区 HEAD：`ef1676cd8327d693dab897c45a234ba91413884e`。仅使用虚构临时样本；没有载入部署 `.env`，没有读取/写入真实企业数据库、启动常驻服务或修改业务源代码。共享任务状态由主执行者统一更新。

## 可复查命令

在仓库根目录执行：

```powershell
& .runtime/company-test/python/Scripts/python.exe doc/baichuan-sdd/ai-assistant/evidence/AI-T02/probe_capabilities.py
& .runtime/company-test/python/Scripts/python.exe doc/baichuan-sdd/ai-assistant/evidence/AI-T02/probe_capabilities.py --web-probe
& .runtime/company-test/python/Scripts/python.exe doc/baichuan-sdd/ai-assistant/evidence/AI-T02/probe_capabilities.py --worker-tests
```

脚本删除继承的数据库/网关/搜索配置，使用环境变量白名单，只在 `.runtime/baichuan-AI-T02-*` 临时目录创建虚构文件。默认探针不打开数据库；`--worker-tests` 只迁移和测试临时 SQLite，结束销毁。外网探针只访问脚本内固定公开 HTTPS 地址，不发送企业或招标数据。脚本包含实际结果断言；非零退出不能认定通过。

## 实测结果

| 能力 | 实际输入和输出 | 结论/限制 |
| --- | --- | --- |
| 模型网关 | 调用现有 `_gateway_request`，返回 `GatewayError.code=unconfigured`，外部调用 0 次 | 适配器存在，但本机隔离环境没有可验证网关配置/许可路由；真实模型生成 NOT_RUN，不据此宣称网关在线 |
| 公开搜索 | 调用 `search_public_query`，返回 `web_search_unconfigured`，外部调用 0 次 | Tavily/Brave/SearXNG 适配器存在，真实搜索 NOT_RUN；不能以 Codex 工具代替应用运行能力 |
| 网页正文 | 现有 `fetch_public_page` 真实读取 `https://example.com/`，173 字符，0.756 秒，文本 SHA-256 `51123be1fcfbaaf0e735569109be1c031cab9d4d96d88ea7bdf7557a56cccc0c` | 正文抓取基本可用；`https://www.python.org/` 被现有状态/重定向/内容格式限制拒绝，`ValueError: page unavailable, redirected or unsupported format`；未绕过限制 |
| 文字 PDF | 两页虚构 PDF，`source_parsers/cli.py` 返回 `completed/native`，两块正文分别定位 page 1/2，0.358 秒 | 可直接复用；不等于业务资格理解已经实现 |
| DOCX | 虚构投标人必需条款及制造商优先项表格；返回中文原文，paragraph 1 和 table 1/row 1，`completed/native`，0.175 秒 | 可提取且保留定位；硬/软条件及主体理解仍属于 AI-T09 |
| 扫描 PDF/OCR | 图像型 PDF，实际识别“虚构测试企业：投标人须具备ITSS二级”“制造商ISO9001证书仅为优先项”；page 1、bbox、置信度 0.9985/0.9796；2.179 秒 | 本地 RapidOCR 真实可用，返回 `needs_review/ocr` 和 `ocr_review_required`，不将识别置信度当证书核验 |
| OCR 关闭/坏文件 | 同一扫描件关闭 OCR：零块，`failed`，`ocr_unavailable/no_text`；坏 PDF：退出 2，`invalid_document` | 明确失败且没有伪造正文；旋转/模糊/加密/超限全集验收尚未执行 |
| XLSX | openpyxl 实际生成并回读三个工作表，约 6040 字节；前导零电话/信用代码/证号以及 `=1+1`、`+SUM(A1:A2)`、`@test` 均强制字符串单元格和文本格式 | 写入器能力通过；业务导出范围、快照、权限、过期和下载仍待 AI-T14 |
| 任务运行器 | 现有 worker 9 项选定测试，临时库迁移到 0045；`Ran 9 tests in 3.327s / OK`，系统检查无问题 | 实测 SQLite 真实写锁恢复、退避、故障传播、关闭功能不领取、租约过期新 fence/旧写拒绝、取消拒绝迟到结果；不等于新的百川任务已经实现 |

首次探针的终端编码显示不正确，已将 stdout 固定 UTF-8 并加入中文精确断言后重跑通过。首次 worker 探针覆盖整个 `TEST` 配置导致 `KeyError: MIRROR`；改为只设置 `TEST.NAME`，随后 9 项全部通过。两次均未访问真实库。

## 可复用模块与配置契约

- `portal.product_intake.run_parser` / `source_parsers/cli.py`：现有资料解析沙箱，环境变量白名单、两并发、最长 120 秒、20 MB 输入、8 MB 输出、网络拒绝；页数 100、OCR 页数 12、字符 200000、块 5000。保留原限制，百川附件权限另加，不借用他人附件 ID。
- 本地已验证 OCR 解释器：`.runtime/company-test/cloud-ocr/Scripts/python.exe`。需将隔离环境 `PORTAL_PRODUCT_PARSER_PYTHON` 明确指向该绝对路径；默认指向 `services/business/.runtime/product-parser-python`，该路径本轮未发现可执行文件，不能仅凭 `PRODUCT_OCR_ENABLED=True` 宣称可用。
- `portal.product_assistant_tools.fetch_public_page`：公共 HTTPS、443 端口、DNS 公网校验、固定 TLS socket、防 DNS rebinding、不跟随重定向、最长 20 秒、512 KB 响应、输出截为 10000 字符。当前接口不返回正文截断标记，百川证据适配需明确记录原始上限和定位，不能声称完整读完超限来源。
- `portal.product_web_search`：Tavily/Brave/SearXNG，每请求最多 6 结果、10 秒连接/20 秒总预算、262144 字节；`search_public_references` 只允许既有设计规范术语，企业补查应使用受公开关键词策略包裹的 `search_public_query`；所有返回值明确 `search_snippet/search_title`，不能升级证书已核实。
- `portal.model_gateway.generate_for_use`：复用路由、模型选择、权限刷新、调用配额和日志；内部 `_request_gateway` 不可作为绕过业务授权的公共接口。冻结新路由前需实际配置和一次最小虚构请求。
- `portal.product_worker`：借鉴短事务、claim、lease/fence、heartbeat、版本与取消规则；独立百川模型与命令，不伪装文档任务或启动无限工作循环。
- 可靠后端隔离解释器：`.runtime/company-test/python/Scripts/python.exe`，Python 3.13.16，Django 5.2.18、pypdf 6.20.0、openpyxl 3.1.5、Pillow 12.3.0、PyMuPDF 1.28.2。与历史锁文件版本不同，必须记录当前版本；不自动升级。`.runtime/verification/Scripts/python.exe` 也可执行，为 Python 3.12.14，已导入 Django/pypdf/openpyxl/fitz；完整测试本轮使用前者。

## 依赖与许可证采用记录

未新增、安装或复制第三方运行代码；复用仓库已有解析器和现存解释器。许可证从当前安装分发包 metadata 只读核对：Django/pypdf 为 BSD-3-Clause，openpyxl 3.1.5 为 MIT，Pillow 为 MIT-CMU；专属 OCR 环境 rapidocr-onnxruntime 1.4.4 为 Apache-2.0，onnxruntime 1.30.0 为 MIT，pypdfium2 5.13.0 metadata 标注 BSD-3-Clause/Apache-2.0 及依赖许可证。模型文件/原生 PDFium 附带许可仍随已有包保留。本次不依赖新下载。

PyMuPDF metadata 标注 AGPL 3.0 或商业双授权；本次仅调用现有安装生成虚构测试 fixture，未将其选作新增生产解析依赖。生产优先复用已有 pypdfium2 沙箱及 pypdf。没有发生需要外部 GitHub 代码采用的难点，因而没有虚构外部研究记录。

## 未完成与恢复入口

AI-T02 能力调查已形成可复查证据，但配置好的真实模型生成及真实公开搜索仍未实测；保留为明确缺口，不将 AI-AC03/04/09/12/13/17 整项标 PASS。下一步可独立开发百川增量底座，同时由 AI-T01 确认真实目标及允许的网关/搜索配置；配置确认后仅用最小虚构公开问题验证调用并记录预算，禁止输出令牌或招标原文。
