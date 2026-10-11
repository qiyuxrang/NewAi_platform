# 后端真实模型接入与业务验收

日期：2026-10-11。千问已实际接通；本轮优先验证后端，RAGFlow 暂缓，前端优化暂缓。真实模型接通不等于完整三件套稳定生成或 Linux 生产部署已完成。

## 实际配置

- 模型标识：`qwen3.8-flash`，官方依据：[千问3.8 Flash](https://help.aliyun.com/zh/model-studio/qwen3-8-flash)。
- 标准北京 OpenAI 兼容 Base URL：`https://dashscope.aliyuncs.com/compatible-mode/v1`，官方依据：[地域与 Base URL](https://help.aliyun.com/zh/model-studio/base-url)。
- 本机私有配置：`.runtime/company-trial/model.env`。API Key 只注入独立模型网关进程，不写入前端、业务数据库或交付测试包；业务数据库保存环境变量名称。
- 本机模型网关：`127.0.0.1:18410`；输出上限 4096 tokens，单次超时 120 秒，支持文本和视觉输入。本机网关并发 2，HR Worker 并发 1。
- 10 条真实路由：产品 `product_assistant / product_blueprint / product_writing / product_review`；人事 `hr_assistant / hr_jd_draft / hr_resume_parse / hr_match_summary / hr_resume_extract`；工程 `engineering_assistant`。
- 启动脚本默认运行 8 个服务；新增 `start --backend-only` 可独立启动 Portal、平台代理、工程 Worker、模型网关、HR Worker、产品 Worker，避免页面就绪失败中断后台生成。当前六个后端及员工页面运行；管理页面就绪失败，未开展前端优化。各服务沿用试用隔离目录和数据库。

`scripts/company-model.py configure` 只配置本机隔离库内的模型与路由，不改变账号或资料授权；`probe` 通过实际业务模型网关发送一次短请求。新机器 `prepare` 自动生成独立服务令牌。配置与复现步骤见 `company-department-trial-guide.md`。

## 已通过的真实调用

| 范围 | 结果 | 证据 |
| --- | --- | --- |
| 上游连接 | 实际千问响应非空；30 输入 / 1 输出 token，约 555 ms | `.runtime/company-test/core/model-provider-probe.json` |
| Django → 独立网关 → 千问 | 配置后及服务重启后均实际连接成功；状态、用量、耗时已留证 | `.runtime/company-test/core/model-cli-probe.json` |
| 部门及人事业务 | 35/35：三部门实际问答、JD 生成/保存/人工确认、BOSS 适配、三份简历处理、CSV、跨部门拒绝 | `.runtime/company-test/core/real-model-business/results.json` |
| 私有配置与启动隔离 | 10/10；仅模型网关收到上游 key，默认启动及后端独立启动、配置边界、新机器私有令牌 | `.runtime/company-test/core/model-private-config-tests.log` |
| 模型配置 CLI | 9/9；隔离 SQLite、事务回滚、冲突、幂等、授权保持 | `.runtime/company-test/core/model-cli-tests-final.log` |
| 模型网关 | 65/65 | `.runtime/company-test/core/model-gateway-backend-final.log` |
| 产品真实蓝图 | 8/8；HTTP 创建→排队→真实 Worker/千问→蓝图保存→等待人工确认 | `.runtime/company-test/core/real-model-product/results.json` |
| 蓝图修复回归 | 核心 28/28、关联 93/93；主代理另用独立库复跑核心 28/28 | `.runtime/company-test/blueprint-fix/` 和 `core/blueprint-parent/regression.log` |

业务测试使用正常登录、身份连接、版本和授权接口，由真实 HR Worker 领取任务；没有拦截接口或替换模型响应。样本为明确标注的合成岗位及候选人，保留在试用材料目录。可复跑脚本为 `.runtime/company-test/core/real_model_business.py`；脚本只打印检查状态。

人事最终批次 `70997aba-8079-453b-9962-6682d1eecd50`：DOCX 高匹配、TXT 缺项、扫描 PDF 各一份，均处理完成。缺项保留 UNKNOWN，评分规则为 `rule-v1-no-age-20260926`；扫描 PDF 保存页码、文本/图像哈希和 `method=vision`，仍标记 `requires_visual_review=true`。

第一次独立批次中的扫描 PDF 曾返回 `vision_review_required`。独立调用同一实际视觉路径成功；第二次整批独立运行 3/3 完成，未调用 retry。首次失败从只读试用数据库导出至 `core/model-acceptance-metadata.json`，不覆盖或隐去。该结果说明样本路径可运行，不证明扫描件普遍稳定。真实视觉识别与本地 RapidOCR 是两条路径，后者的 Python 3.13 依赖安装失败仍待处理。

## 产品与生产交付边界

本机采用 `source_only_preview`，按用户要求跳过 RAGFlow。初始蓝图测试未进行联网检索；用户随后要求先联网再生成，已实际检索和核实八份官方参考，并通过正常来源上传接口加入新任务。这是外部联网检索后导入资料，业务系统自身的自动联网适配器尚未配置。云端部署候选包仍采用 `ragflow_required`。完整三件套的技术方案 50000 字、可研 70000 字、来源、内容、渲染和正式发布条件均保留，正式发布仍关闭。

首次真实产品蓝图请求被原始条件严格校验拒绝：模型改写了条件，`condition_missing` 被后台泛化为 `execution_failed`。已修复提示、输出校验和失败码：原始条件必须逐字保留；JSON/语义校验共用最多一次纠正，仍使用原有授权、租约和调用额度；来源、模板及条件不合法的结果不保存。

主代理通过正常 API 创建新的合成项目，真实千问蓝图已保存，任务 `f24b95d4-7265-45dd-a60f-1e2a0f182ddc` 停在 `WAITING_REVIEW / BLUEPRINT`，没有自动批准或生成正式成果。初始失败在 `core/real-model-product/initial-results.json`、`initial-task.json` 保留；修复后 `results.json` 为 8/8，完整蓝图见 `task.json`。本例使用人工结构化输入，不能代替所有上传文件组合或完整长文验收。

用户随后明确要求“蓝图确认”。已通过正常确认接口提交该版本及哈希，HTTP 201，批准记录 `bddf24ef-b566-4afa-baa5-9a5dab62f763`。确认后 Worker 已进入 `RUNNING / WRITING / generate_outputs`，目标为技术方案、可研报告和演示文稿；此记录代表确认与启动成功，不代表三件套已生成完成。证据 `core/real-model-product/confirmation-results.json` 和 `post-confirmation-task.json`。预算、工期及列明缺失资料仍保持待确认。

历史全量 Django 1244 项（1218 通过、26 跳过）、平台 47/47、网页 39/39 见部门总报告；39 项网页检查发生于本次模型接通前，本轮没有重新开展整套网页验收。专项与历史检查有重叠，不能相加。

最新任务为 `ddc6d238-7de5-4416-ac5e-09093fad9952`，旧任务正常取消并留存快照；新任务保留已确认八章目录与原条件，补充项目事实及八份已核实公开来源，通过正常蓝图确认接口启动 `generate_outputs`。引用版本确认依据用户“蓝图已经人工确认，继续生成”和“先联网检索，再生成三件套”的指令；缺失预算、工期等仍待确认。过程及最终结果见 `three-piece-web-generation-20261011.md`。

续写发现真实模型重复旧段落，新增正文语义校验进入原有最多一次纠正重试，重复不计字数且不会覆盖已保存内容。已确认的预览蓝图缺项只允许继续生成待审草稿，审查仍保留不通过及待确认标记，其他事实、数字、来源、冲突及正式发布门禁仍有效。专项 worker/结构化输出 44/44，长度/集成 38/38；主代理独立复跑核心 44/44。日志见 `core/triad-worker-parent/regression.log`、`triad-worker-fix/novelty-tests.log` 和 `length-and-integration-tests.log`，不等于本轮重新执行全部历史回归。

下一步后端验收重点是完整长文三件套多次生成和恢复、更多扫描材料及失败重试、目标 Linux Docker/PostgreSQL/Office 渲染；RAGFlow 待用户在另一台电脑接入，前端待后端稳定再优化。服务器尚未准备，当前交付为部署候选包与可复现材料，不声明云部署已验收。
