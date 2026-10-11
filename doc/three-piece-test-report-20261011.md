# 产品事业部三件套测试记录（2026-10-11）

结论：本地合成样本的文件生成、Office 打开与逐页渲染、下载授权、预览完整性及前端操作通过。发现的 PPT 图片拉伸已修复。两组回归测试共 **89 项通过，无跳过**。这次没有调用真实模型或 RAG，尚不能判定已达到 Linux 云服务器稳定生成完整业务三件套的最终交付标准。

## 文件实测

使用独立测试数据库、明确标注的合成资料、人工编写的短章节和图示输入；实际调用项目的 DOCX/PPTX 生成器及 Edge/Mermaid，不 mock Office 文件或图像生成。生成实物保存在 `.runtime/three-piece-generation/run-20261011-144936-9744`；修复后的 PPT 保存在 `.runtime/three-piece-generation/ppt-contain-20261011-145712-17340`。

| 成果 | 实际内容结构 | 实际渲染 | 原始生成文件字节数 |
| --- | --- | --- | ---: |
| 技术方案 DOCX | 15 张 Mermaid 图、目录、正文、设备清单 | Word 16，14 页 | 900985 |
| 可研报告 DOCX | 20 张 Mermaid 图、目录、正文、待确认事项 | Word 16，17 页 | 1249963 |
| 修复后汇报 PPTX | 5 页、1 个原生图表和内嵌 XLSX、来源备注 | PowerPoint 16，5 页 | 240776 |

主代理用项目原有 Office 渲染程序串行执行，Word 仅处理复制件并刷新目录、域和分页；原始文件哈希保持不变。随后逐页检查两份 Word 的 31 页和修复后的 PPT 全部 5 页。中文、图示、目录、页码和图表可显示，未发现页面文字越界或明显遮挡。短样本部分页面留白较多，PPT 摘要仍需结合真实项目资料审核；没有授予业务审批、正式发布或完整内容验收。

文档技能的标准 `render_docx.py` 因本机缺少 `soffice.exe` 未能执行；实际页面检查采用项目现有 Microsoft Office 16 → PDF → PNG 链路，不能当作 LibreOffice/Linux 渲染验证。

原始 DOCX 与 Office 刷新目录后的处理副本哈希不同，这是预期的域缓存更新。测试样本 ZIP 顶层提供处理副本，`original-generated` 内保留下载测试所用原始 DOCX；两者均为合成测试样本。

| 文件版本 | SHA256 |
| --- | --- |
| 技术方案原始生成件 | `94cefea335c4b1df79a2cf7cc1d13884b66ddef52e39a0872734c8e9a5818d07` |
| 技术方案 Office 处理副本 | `8814a1a07e822337568c66c2216344da1d49363a1dc199e17a17a83fb607696a` |
| 可研原始生成件 | `074ceb29d5de76186d6f091d72658af076675232d316793c213ed6860d95f459` |
| 可研 Office 处理副本 | `0811ccead4337f09943675333c9be78eefc0a344182ce8c7ef5de38a5a6058ab` |
| 修复后 PPT | `9e5a95b6f1108f7c3b3f0b8407296f4badf9deb796c10f9b7db42b5f3e5592de` |

## 门槛、接口与界面

- **原始长度门槛保留**：技术正文 1109 字符、可研正文 1454 字符，真实编排入口分别按 50000/70000 字符要求返回 `output_length_below_target`，输出数为零。随后通过底层渲染入口制作结构样本；没有用短样本冒充完整 worker 生成成功。
- **真实文件下载接口**：原始三份生成文件的 owner、指定 reviewer 下载返回 200，字节 SHA 与实物一致；外部用户和撤销后的 reviewer 返回 404。新输入版本使当前下载返回 409；明确请求历史版本可下载原字节且标记非当前版本。记录共 15 项，使用真实 Django 流式响应。
- **真实页面预览接口**：在独立数据库及文件副本中，用真实 Office PDF/PNG 构造带哈希的规范预览元数据。28 项检查通过，owner/reviewer 共 72 次逐页读取，PNG 字节、SHA、类型均与 Office 输出一致。越权、配置/角色撤权、旧输入版本、图片内容或元数据哈希篡改、缺规范证据均被拒绝。旧版本即使加 `history=1` 也不能使用当前预览。
- **状态保持**：预览未写审批、交付状态或 `page_views`；按原设计增加了预览访问审计事件。原数据库前后 SHA 相同。预览元数据明确标为测试构造，不代表生产 worker 已完成渲染和绑定。预览 API 本轮使用首次 PPT 的页图；修复 PPT 的实际页图另由主代理和最终 UI 检查验证。
- **前端**：生产 React UI 在 1440×900、1280×720 下的 14 个关键场景通过，覆盖三类成果选择、蓝图确认、运行态、失败续跑、下载、预览、撤权及旧版本拒绝。最终使用两份原始 DOCX、修复后的 PPT 和实际 Office 首页复核：6 次浏览器下载逐字节一致，中心/侧栏共 12 次首页预览的图片字节、尺寸、RGBA 像素一致；无页面错误及横向溢出。界面网络响应使用明确的测试夹具，并非浏览器经网关访问生产 worker 的端到端测试。

## 发现并修正的问题

1. **PPT 图片拉伸**：原先同时指定容器宽高，将 16:9 图片变为不相关比例。`simple_presentation.py` 增加等比 contain 放置并在原容器内居中，封面及报告图共用；无裁切，图片字节、正文、来源备注和原生图表保持。新 PPT 已重新生成、实际打开、逐页渲染检查。
2. **过期重试用例**：原 fixture 写入输入之外的数字，因此正确触发 `unsupported_number`；旧预期还把长文抽检完成视作 `COMPLETED`。仅修正测试数据、mock 参数和预期，断言重试复用原两份 Word 的 ID/哈希，长文成功后仍为 `WAITING_REVIEW`、要求人工全文审核且无自动审批。生产 worker 未修改。
3. **8 项测试跳过**：来源及恢复测试写死旧 Windows Python 路径，改用配置的 `PRODUCT_DOCUMENT_PYTHON`。本次实际执行了原先跳过的来源大小/数量边界、来源备注和真实 PPT 渲染测试。

## 回归与证据

主代理第一组测试：`test_product_three_drafts`、`test_product_output_preview`、`test_product_worker_transactions`、`test_product_output_length`、`test_product_pair`；**71 项，128.328 秒，OK，无跳过**。

主代理第二组最终复跑：`test_presentation_renderer_cache`、`test_product_presentation_recovery`、`test_product_presentation_sources`、`test_presentation_image_placement`；**18 项，11.533 秒，OK，无跳过**。最终日志在 `.runtime/three-piece-test/ppt-parent-regression-final.log`；先前失败日志保留用于追溯。子代理的另行 3 项和 18 项复跑不重复计入上述 89 项。

主代理独立核对了生成文件哈希、Office 渲染原件不变、全部页面图、页面文字边界、最终 UI 下载和像素记录、预览 API 页图哈希与原数据库不变；检查结果在 `.runtime/three-piece-test/parent-file-audit.json`、`parent-evidence-check.json`、`visual-review.json`。

复现脚本和专项证据：

- `.runtime/three-piece-generation/run_actual_generation.py`、`verification-results.md`、各 run 的 `verification.json`。
- `.runtime/three-piece-preview-test/verify_real_previews.py`、`run-20261011-145943-11624/verification.json`。
- `.runtime/three-piece-ui/report.md`、`report-final.md`、`results-final.json`、`artifact-validation-final.json`。
- `.runtime/three-piece-test/audit_rendered_files.py`、`verify_evidence.py`、`environment.md`、各渲染目录的 `render.json`、PDF 和每页 PNG。

## 尚未完成的最终交付验收

本机没有 Docker、已安装的 WSL 或 LibreOffice，也没有准备好的云服务器。私有 `.env` 和当前进程没有可确认的模型/RAG 配置；配置模板的非空项不作为已配置凭据使用。

仍需在 Linux Docker 环境实际构建启动，以真实项目资料和已配置模型/知识库完成满足 50000/70000 字符要求的生成、完整正文与事实审查、LibreOffice 目录及页面渲染、网关/浏览器端到端下载预览、失败续跑和重复生成稳定性验证。此前完成的云部署候选包继续保留，本次不替代这些最终验收。
