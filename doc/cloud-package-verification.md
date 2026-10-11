# Linux Docker 部署候选包验证记录

日期：2026-10-11。执行主机：Windows。用户已确认服务器尚未准备，本阶段交付部署包和本地验证结果。

补充日期：2026-10-12。本地 OCR 运行时与离线验收检查修复如下；服务器仍未准备，未执行 Docker 镜像构建或真实 Linux OCR。

## 已实施

- `deploy/cloud/`：Linux Docker Compose、四个应用镜像构建文件、Caddy HTTPS 入口、独立数据库初始化、配置生成及校验、备份脚本、镜像检查与合成渲染烟测。
- 产品默认请求技术方案 DOCX、可研 DOCX、演示 PPTX；保留既有长度、资料授权、蓝图审批、内容核对及版本检查。
- 显式 Linux LibreOffice Writer/Impress 渲染后端：独立输入副本、profile、UNO pipe 和进程会话，超时回收仅作用于本次进程；保留 Windows Word 渲染路径。
- 渲染证据核对源文件、目录缓存、输出文件及逐页图片哈希；实际渲染和人工视觉/业务确认仍分别记录。
- 产品工作台采用浅色任务导航、中央项目工作区、右侧可折叠成果面板；真实 API 提供项目、审批、补充、续跑、版本和授权下载。
- 三件套草稿通过独立授权预览接口读取真实逐页 PNG，证据绑定最终文件哈希；旧候选继续使用原接口，草稿预览不写正式审批或逐页验证记录。无标准预览证据的历史草稿不可预览，需生成新的内容版本；仅重新排队同一生成版本会复用原成果，不会补建证据。历史下载按原权限保留。
- 限定生产跨域来源；依赖锁定，冻结模板清单与当前脚本摘要和字节数同步，模板和规则内容保持原样。
- cloud 主业务与文档解释器保留 Python 3.13；资料解析采用项目既有的独立 Python 3.12 方案，复制 `source_parsers/requirements.txt` 的 19 个精确包版本，增加 OpenCV 系统库，并将 Compose 解析器路径设为 `/opt/product-parser/bin/python`。
- `image-checks` 增加真实离线 OCR：生成中文、英文和数字 PNG 与无文字层 PDF，调用原生产解析 CLI；只有两者都返回实际 OCR 内容块且识别出已知文字才通过。缺依赖、空识别及部分失败会终止检查，不调用模型或数据库。

## 已执行的本地验证

| 检查 | 结果与边界 |
| --- | --- |
| Python 依赖 | 隔离 Python 3.13.16 环境安装 `deploy/cloud/requirements.lock` 成功；126 个已安装包兼容性检查通过。此处为 Windows wheel，不能证明 Linux 镜像可构建。 |
| OCR 兼容元数据 | 查询官方 PyPI 的 19 个精确 OCR 包版本；Python 3.12 满足全部声明且都有 Linux amd64 wheel。RapidOCR 1.4.4 要求 <3.13，NumPy 2.5.3 要求 >=3.12，因此采用独立 3.12。仅元数据审查，不等于实际 Linux 安装。 |
| Windows 真实本地 OCR | 独立 `.runtime/company-test/cloud-ocr` Python 3.12.14 安装 19 个锁定包，`uv pip check` 通过；实际执行 `image_checks.py --ocr-worker`，PNG 与无文字层 PDF 各返回两个 OCR 内容块，英文、数字及中文核验通过；实际识别子进程在 `runpy` 执行原 CLI 前可构造未连接 socket，执行后实际尝试三种 socket API，均由原 CLI 禁用钩子明确拒绝并记录证据。检查脚本未另装替代钩子。无模型调用，未验收操作系统网络隔离；未安装到共享业务环境，不证明 Linux OCR 或实际扫描件准确率。 |
| OCR 失败拒绝 | 另建独立 3.12 环境，仅安装其余 18 个包而缺 RapidOCR；实际合成识别被检查拒绝并返回非零。原 7 项部署包检查增加空结果、部分结果及 `ocr_unavailable` 拒绝断言，最终 7 项均通过。 |
| 平台回归 | `python -m unittest discover -s platform/tests -p test_*.py`，33 项通过。 |
| CORS | 实际应用 TestClient 校验指定来源允许、其它来源拒绝；不依赖数据库。 |
| 部署包结构及备份 | `python deploy/cloud/validate_package.py`，7 项通过；覆盖路径、私有配置排除、网络/端口、锁定依赖、拒绝覆盖配置；使用 Git POSIX shell 完成 `sh -n` 和 6 种模拟 Docker 行为，验证停机顺序、失败恢复与拒绝不一致备份。未运行真实 Docker 备份。 |
| Mermaid | 按原 pnpm 锁文件安装和构建成功；`node --test qa/*.test.mjs`，6 项通过。 |
| 产品后端 | Python 3.13.16 下，Linux 渲染契约、三件套、worker 事务、原渲染、生产就绪、文档回归，共 95 项检查，94 项通过、1 项因需要 Linux 跳过。实际可编辑 PPTX 生成和原生图表 OOXML 审计已执行；UNO 调用为替身测试。 |
| 主代理复核 | 独立复跑上述后端模块；初次本地测试漏设 `PORTAL_HTTPS=0`，导致 7 项登录被 HTTPS 重定向。补齐仅测试用环境后，这 7 项全部通过；生产 HTTPS 配置保持启用。 |
| 草稿预览整合 | 新预览、Word 证据生成和原候选发布回归共 30 项通过；主代理独立复跑新 API 测试，验证真实会话返回合成 PNG、哈希、撤权、版本失效和篡改拒绝。实际 UNO 仍未执行。 |
| 员工前端 | 原 npm 锁文件 `npm ci` 后，TypeScript 与 Vite 生产构建通过；存在全站主 JS bundle 大于 500 kB 的构建提示。 |
| 管理前端 | 原 npm 锁文件 `npm ci` 后，Next.js 16.1.6 生产构建通过，生成 standalone 输出。 |
| 浏览器 | Playwright + Edge，1440×900 与 1280×720，22 场景通过，覆盖新建、读取失败、蓝图审核、运行中、重试、三件套成果与草稿预览、补充、撤权、旧候选、无证据及预览失败。候选兼容修正后另复核 8 个相关场景全部通过。数据为标注的网络测试数据，未执行真实模型生成。 |

唯一跳过的原生 Linux 测试：`portal.tests.test_libreoffice_rendering.LinuxProcessIsolationTests.test_native_timeout_kills_owned_descendant_and_preserves_unrelated_session`。

本机详细证据位于 `.runtime/linux-rendering/verification-results.md`、`.runtime/linux-rendering/final-tool-results.json`、`.runtime/linux-rendering/draft-preview-tests.log`、`.runtime/frontend-review/report.md`、`.runtime/frontend-review/results.json`、`.runtime/frontend-review/preview-results.json`。主代理审查了新建、成果及 1280 项目截图，并核对后端与部署代码；最终 TypeScript 与 Vite 构建由主代理再次执行通过。`.runtime` 为本地验证资料，不进入部署镜像。

2026-10-12 OCR 补充证据：`.runtime/company-test/cloud-ocr/evidence/verification.json`、`official-package-metadata.json`、`dependency-check.log`、`windows-real-ocr.log`、`missing-dependencies-refused.log`、`package-static-seven.log`。仅包含合成验证和公开包元数据；运行时、测试证据均由现有 `.gitignore` / `.dockerignore` 排除，不上传 GitHub 源码或进入镜像。

2026-10-12 云端公司预览配置补充：用户已授权暂不连接 RAGFlow，因此配置工具新增显式 `--product-knowledge-mode source_only_preview`，默认仍为 `ragflow_required`，未知或缺失模式拒绝。check 仅验证已保存私有文件，不接受临时模式覆盖。真实离线配置与包检查8/8通过，公共云包源码及依赖前后SHA一致，证据 `core/cloud-preview-parent/explicit-preview-parent01-result.json` 与同名日志；独立只读范围复核见 `handoff-boundary-audit/cloud-preview-fixed-01-results.json`。生成配置保留独立凭据、模型与知识开关默认关闭，不输出凭据，不改变业务权限、旧知识授权复查或Compose正式发布关闭设置。这是配置工具验证，不是Docker/Linux或实际三件套验收。

## 目标云服务器仍须执行

1. 按 `deploy/cloud/README.md` 生成私有配置，并用实际 Docker Compose CLI 校验；本地 CLI 下载因网络超时未完成，当前结构检查不替代此步骤。
2. 冷构建 OpenClaw 和全部应用镜像，执行 `portal-init image-checks`，确认主 3.13 与独立 OCR 3.12 依赖、实际离线 PNG/扫描 PDF 识别均通过；再初始化并验证数据库、TLS、登录、首次改密、账号绑定和授权。
3. 执行真实 Writer/Impress、中文字体和 Mermaid 合成烟测，逐页查看 Word/PPT 排版、目录、页码、缺字和图表裁切。
4. 配置并验证真实模型、用户路由与上传资料权限；当前授权的公司测试显式使用 source_only_preview，先核实并上传资料、确认蓝图，再验收待审三件套生成、预览和下载。该模式不代表自动联网适配器或RAGFlow已接通。恢复ragflow_required时另行完成RAGFlow个人资料授权及实际检索，不得自动降级或复用已撤销授权。
5. 按交付标准执行多样本生成、worker 重启/异常恢复、并发隔离、资料撤权与独立备份恢复验收。

正式发布继续关闭。真实 Linux 渲染和三件套稳定生成尚未验收，部署候选包不能作为最终生产验收通过的证明。

OCR 一手来源：[RapidOCR 1.4.4](https://pypi.org/project/rapidocr-onnxruntime/1.4.4/)、[NumPy 2.5.3](https://pypi.org/project/numpy/2.5.3/)、[ONNX Runtime 1.30.0](https://pypi.org/project/onnxruntime/1.30.0/)、[OpenCV 5.0.0.93](https://pypi.org/project/opencv-python/5.0.0.93/)、[CPU 安装说明](https://onnxruntime.ai/docs/install/#install-onnx-runtime-cpu)。人事扫描简历仍按原模型视觉路径执行；这次修复没有改变扫描 JD 拒绝策略。
