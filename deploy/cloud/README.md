# Linux 云部署包

本包为单台 Linux 服务器的部署候选：员工端、管理端、业务门户 API 与后台、模型网关、产品 worker、PostgreSQL 和 Caddy TLS。产品目标是技术方案 Word、可研 Word、汇报 PPT 三件套。正式生成须真实模型与 RAGFlow 的个人资料授权；正式发布审批默认关闭。

当前完成的是源码和配置结构校验，以及在本机隔离的 Windows Python 3.13.16 中安装最终 requirements.lock 和检查126个包的兼容性，均已通过。当前机器不能运行 Docker，也没有云服务器；**镜像冷构建、Linux LibreOffice 渲染、公网 TLS、真实模型/知识服务、实际三件套业务验收尚未执行**。requirements.lock 的版本来自现有 Python 3.12 验证环境，并已完成上述 Windows Python 3.13 安装验证；Linux wheel、系统库和跨平台兼容性仍必须由下述镜像检查确认。不得把此文档或合成烟测报告视为上线批准。

## 服务器与目录

准备独立 Linux amd64 Docker 主机，安装 Docker Engine、BuildKit、Compose v2 与 Python 3。宿主内核与容器安全策略必须支持 `pidfd_open` / `pidfd_send_signal`；镜像检查会实际打开本进程 pidfd 并检查信号接口，渲染不使用全局进程清理替代隔离。建议试运行至少 8 vCPU、16 GB RAM、100 GB SSD；这只是起步容量，OpenClaw 冷构建与每员工容器可能需要更多内存，须压测确认。三个独立域名 A/AAAA 指向服务器；安全组仅公开 80/443（含按需 443 UDP），SSH 限管理来源。不要公开 PostgreSQL、Docker TCP socket 或员工容器端口。

将项目源码放入私有目录，例如 `/srv/aicompany`，以下命令从 `deploy/cloud` 执行。不要使用根目录的 Windows `docker-compose.enterprise.yml`。所有持久数据使用 Docker volumes；不得运行 `down -v` 或 `docker volume prune`。

```sh
cd /srv/aicompany/deploy/cloud
python3 configure.py generate --app-domain work.your-company.cn \
  --admin-domain admin.your-company.cn --portal-domain portal.your-company.cn \
  --email ops@your-company.cn
python3 configure.py check
chmod 600 .env
docker compose --env-file .env -f compose.yml config --quiet
```

生成器拒绝覆盖已有 `.env`，生成独立随机凭据并且不打印密码。私有 `.env` 不得进入聊天、源码、镜像、公开日志；在密码管理器中保管。`config --quiet` 避免把 Compose 展开后的凭据输出到终端。模板中的示例域名和空密钥故意不能用于上线。添加自定义 JSON 授权时使用单行 JSON；不要使用未经转义的 `$`、换行或 shell 引号作为 env 值。

## 冷构建与运行时镜像

业务镜像基于 Python 3.13 Debian bookworm，安装 LibreOffice Writer/Impress、系统 UNO Python、Chromium、中文字体与 PDF 工具。业务和文档 Python 是 `/usr/local/bin/python`；资料解析与本地 OCR 使用独立 Python 3.12 `/opt/product-parser/bin/python`，按现有 `source_parsers/requirements.txt` 安装 19 个精确依赖，避免把 RapidOCR 装进 3.13。UNO 必须使用 `/usr/bin/python3`，不能用 pip 包替代系统 UNO。Mermaid 从锁文件构建，禁止把本机 node_modules 或 dist 当作冷构建成功证据。

`image-checks` 会分别检查主业务和 OCR 环境的依赖，再用中文字体生成 PNG 与无文字层扫描 PDF，调用实际资料解析 CLI。两份文件都必须识别出英文、数字和中文，并返回 OCR 内容块；依赖缺失、空识别、原生文字替代、部分失败均拒绝通过。实际识别子进程先确认可以构造未连接的 socket，再用 `runpy` 执行原解析 CLI；原 CLI 自行禁用 Python socket，识别后实际尝试 `socket`、`create_connection`、`getaddrinfo`，仅原钩子明确拒绝才通过并记录证据，检查脚本不另装替代钩子。普通连接或 DNS 失败不能当作禁用成功。此处验证的是 Python socket 调用禁用，尚未测试操作系统网络隔离；不调用模型、不读取数据库。此检查只能证明合成样本可用，不能代替实际扫描件准确率验收。

OpenClaw enterprise Dockerfile 需要先构建它指定的 `aicompany-claw-core-build:20261008`，然后构建包含 Bridge 的最终镜像。两个 Dockerfile 及桥接锁文件/部署模板均在源码内；没有发现必须使用预编译私有核心的依赖。以下两步仍需真实执行；现有 core 构建允许 A2UI fallback stub，不能因此宣称 Canvas 功能已验收。

```sh
cd /srv/aicompany
docker build --target build -f openclaw/Dockerfile.enterprise-core \
  -t aicompany-claw-core-build:20261008 openclaw
docker build -f openclaw/Dockerfile.enterprise \
  -t aicompany-claw:20261008 openclaw
cd deploy/cloud
docker compose --env-file .env -f compose.yml build --pull
docker compose --env-file .env -f compose.yml run --rm --no-deps portal-init image-checks
docker compose --env-file .env -f compose.yml run --rm --no-deps --entrypoint python gateway -m pip check
```

网络下载失败、Linux 3.13 无 wheel、依赖冲突或构建失败应作为阻塞处理，不能跳过检查、临时改为未锁定依赖或声称已构建。企业 OpenClaw 镜像中原有“Windows worker”注释不适用于本包：这里 Word 渲染由独立 Linux business worker 执行。每用户容器通过同机器 Docker socket 创建，接入 `aicompany-cloud-internal`；因此服务器应专用于这一部署。这个网络有外网出口，供模型/RAGFlow调用；名称中的 internal 不表示 Docker `internal: true` 的无外网隔离。

前端和管理端使用 cloud 专属 Dockerfile、根目录 build context 与统一 `.dockerignore`，不把本机环境文件带入 `COPY .`。源码内不提供缺失的旧 `services/business/frontend`；主员工前端是正常工作入口，门户域名根路径跳到员工域名。门户 `/login`、`/password` 使用本包最小同源页面调用原登录、CSRF 和改密 API；`/admin/` 使用原 Django 管理后台。

## 初始化、账号和模块授权

```sh
docker compose --env-file .env -f compose.yml up -d postgres
docker compose --env-file .env -f compose.yml --profile setup run --rm portal-init init
docker compose --env-file .env -f compose.yml --profile setup run --rm portal-init manage bootstrap_admin business_admin
docker compose --env-file .env -f compose.yml up -d
docker compose --env-file .env -f compose.yml ps
```

PostgreSQL 首次初始化创建 `platform` 和 `enterprise_portal` 两个数据库；它的 init 脚本只在空数据卷运行。业务 migrate、seed、collectstatic 只由明确的 init 作业执行。平台 gateway 现有启动逻辑会建立/补齐自己的表并创建 `.env` 中管理账号；对已有账号不重置密码。升级前仍需迁移排练和备份，平台自动补列不能替代正式迁移审查。

业务管理员是独立账号，`bootstrap_admin` 交互读取密码、不授予 Django 超级用户。访问 `https://PORTAL_DOMAIN/login` 完成首次登录与强制改密，然后重新登录进入 `/admin/`。后台创建员工、分配角色、启用产品模块；管理员身份不自动取得所有业务正文/资料权限。平台管理账号访问 `https://ADMIN_DOMAIN`，从私有 `.env` 安全读取初始密码；平台员工账号与业务账号须通过原员工端绑定流程关联。业务账号更换、停用、撤权与会话失效需实测。

缺失旧门户 SPA 的 `/ops`、`/centers` 页面不会被本包复造；Django 管理后台的“返回运维”链接会经门户 fallback 回到员工端。此限制不影响原 `/admin` 配置表与业务 API，但必须在验收报告中保留。

## 模型与知识资料

模型 Key 放 `.env` 的 `PORTAL_MODEL_KEY_PRIMARY`（可扩展相同前缀变量）。独立模型网关的 `MODEL_GATEWAY_ALLOWED_BASE_URLS` 必须明确允许真实 HTTPS 基础地址；门户 Provider 的 `api_key_env` 填变量名而非明文 Key。从原 Django `/admin/` 配置 Provider、GatewayModel、ModelRoute 与按用户/角色的 ModelRouteOption，真实连接测试成功后才启用。产品默认路由为 `product_blueprint`、`product_writing`、`product_review`、知识处理为 `product_knowledge`，属于产品模块。前端平台 `PLATFORM_DEFAULT_MODEL`、`PLATFORM_MODEL_IDS` 与对应平台提供商配置也需与可用模型一致。

只有负责人明确授权后才设 `PORTAL_PRODUCT_MODEL_CALLS_ALLOWED=1`。RAGFlow 是外部服务，不包含在本 Compose；设置 `PORTAL_PRODUCT_KNOWLEDGE_URL`、`PORTAL_PRODUCT_KNOWLEDGE_ALLOWED_URLS`、令牌环境变量名称和其真实值、`PORTAL_PRODUCT_KNOWLEDGE_AUTHORIZATIONS` 个人授权映射及授权 revision，再打开 knowledge enabled/AI calls 两个开关。RAGFlow 地址必须为 `https://真实域名/api/v1/retrieval`、默认443端口，允许名单包含完整URL。授权映射为业务用户数字ID → dataset ID → 允许的 document ID 数组，例如 `{"42":{"approved_dataset":["approved_document"]}}`（仅展示格式，不是真实授权）；每用户最多4个dataset，每dataset最多100个文档，标识只能使用字母数字下划线短横线。令牌变量可命名 `RAGFLOW_SERVICE_TOKEN`，在私有.env新增实际值，`PORTAL_PRODUCT_KNOWLEDGE_TOKEN_ENV=RAGFLOW_SERVICE_TOKEN`。授权变更递增 `PORTAL_PRODUCT_KNOWLEDGE_AUTHORIZATION_REVISION` 并重新创建服务；按当前 `portal/product_knowledge_service.py` 校验格式操作，禁止默认共享全库授权。业务模型路由可经原 Django admin 配置；知识授权来自受控环境配置，不存在自动创建全用户知识授权的后台按钮。

默认 `PORTAL_PRODUCT_BLUEPRINT_KNOWLEDGE_MODE=ragflow_required`；该模式没配置知识资料来源时任务失败是预期阻塞，不会自动降级。当前公司试用已明确授权暂不连接 RAGFlow，可在首次生成私有配置时显式选择上传资料预览模式：

```sh
python3 configure.py generate --product-knowledge-mode source_only_preview \
  --app-domain work.your-company.cn --admin-domain admin.your-company.cn \
  --portal-domain portal.your-company.cn --email ops@your-company.cn
python3 configure.py check
```

该选择只生成待审草稿，不伪造知识库命中，也不自动打开模型或知识服务授权。保留 `PORTAL_PRODUCT_KNOWLEDGE_ENABLED=0` 与 `PORTAL_PRODUCT_KNOWLEDGE_AI_CALLS_ALLOWED=0`；模型连接、用户路由授权、上传资料核对、蓝图确认与全文审核仍分别执行。联网材料须先核实再上传，不能把本模式当作已接入自动联网搜索。已有 `.env` 时不要删除或重新生成凭据；在私有配置中明确修改上述模式与知识开关，再执行 check。check 只验证保存的配置，不能通过命令行临时覆盖模式。若旧任务曾检索 RAGFlow，其已绑定知识授权仍会重新核对，切换预览模式不能绕过撤权。

恢复 RAGFlow 时显式改回 `ragflow_required`，完成服务、资料授权与真实检索检查。修改 `.env` 后对业务服务执行 `up -d --force-recreate`；单纯 `restart` 不加载新环境。`PORTAL_PRODUCT_FORMAL_RELEASE_ENABLED=0` 固定在 Compose，须审批后审查专门变更才启用正式发布。预览模式与配置检查通过不等于正式发布或 Linux 业务验收通过。

## 健康、Linux 渲染与业务验收

```sh
docker compose --env-file .env -f compose.yml ps
docker compose --env-file .env -f compose.yml logs --tail=100 portal product-worker model-gateway gateway
curl --fail https://work.your-company.cn/api/ping
curl --fail https://portal.your-company.cn/health/
docker compose --env-file .env -f compose.yml exec portal python /app/cloud_entrypoint.py manage check --deploy
docker compose --env-file .env -f compose.yml exec portal python /app/cloud_entrypoint.py manage check_production_readiness --json
docker compose --env-file .env -f compose.yml run --rm --no-deps portal-init render-smoke --output /data/product/cloud-smoke-001
```

合成烟测生成短 DOCX、中文 Mermaid 流程图、PPT，调用真实 Linux LibreOffice 刷新目录、导出 PDF，并核对 PDF 中文文字和页数。`cloud-smoke-001` 必须是新目录，重复执行换目录；报告和 PNG 在 business_data 的产品目录。必须取出查看 Word 每页与 PPT 页图，核对目录页码、中文缺字、分页、图片裁切。这只是合成渲染与依赖检查，不代替真实输入到三件套的业务验收。

健康检查覆盖 PostgreSQL、业务 portal、模型网关和平台 gateway；它们不能证明 worker 真实领取任务、模型授权或知识召回成功。`check_production_readiness` 默认保留 external gates；不要用 `--allow-external-gates` 掩盖上线阻塞。产品三件套验收需真实已授权资料、真实模型、生成三份可编辑文件、Word目录刷新与PDF逐页检查、PPT无裁切、来源引用/知识撤权/账号隔离、worker重启与持久恢复，以及负责人对事实、术语、预算和正式发布的审批。

## 一致备份、恢复与回滚

在专用单部署主机执行 `sh backup.sh /srv/backups/aicompany-YYYYMMDD-HHMMSS`。脚本记录原运行的 Compose 服务，先关闭 edge/gateway 和所有其他业务服务、worker，保持 PostgreSQL 运行；随后枚举并停止当前运行的员工容器，在数据库备份前确认目标网络标签下已无运行中的员工容器，防止新请求重启容器破坏一致性。备份两数据库 custom dumps、Compose 非数据库 volumes 和所有 `openclaw-data-*` 动态用户卷、私有配置及镜像信息；正常或失败退出均仅恢复保存列表中的业务服务（edge最后），再恢复原运行的员工容器，不启动原本停用的服务。恢复失败返回非零状态并提示检查保存列表。要求目的目录不存在，禁止共享 Docker 主机上无差别备份其它租户。运行前确保 `alpine:3.22` 镜像可用及足够空间；数据库与用户文件必须作为同一套备份恢复。只有存在 `BACKUP_COMPLETE` 的备份才表示数据备份完整完成；还须确认脚本返回码为0，才能认为服务恢复成功。将备份加密保存到服务器外，定期恢复排练。

`agent_data` 不是动态员工实际文件卷，实际卷名由平台 `openclaw-data-<用户短ID>` 创建；仅备份 Compose volumes 会漏员工文件。数据库包含授权/会话，业务卷包含上传文件/输出，Caddy 卷包含证书；备份和 `.env` 同属私密数据。

恢复到隔离的新服务器并使用原项目名/卷名/发布镜像；先检查备份清单和归属，不直接覆盖在线生产卷：

1. 恢复私有 `.env` 和原源码/镜像，`python3 configure.py check`，DNS 暂不切换。确保恢复目标没有运行中的员工容器/业务服务。
2. 对 `volumes.txt` 每个卷执行 `docker volume create <原卷名>`，再用 `docker run --rm --network none -v <原卷名>:/target -v <备份绝对路径>/volumes:/backup:ro alpine:3.22 sh -c 'tar -C /target -xzf /backup/<原卷名>.tar.gz'`。必须恢复到新空卷，保留 tar 中 UID/GID；不要自行清空在线卷。
3. `docker compose --env-file .env -f compose.yml up -d postgres`，等待 healthy。两数据库由首次 PostgreSQL init 创建。恢复：

```sh
docker compose --env-file .env -f compose.yml exec -T postgres sh -c \
  'exec pg_restore -U "$POSTGRES_USER" --clean --if-exists --no-owner -d platform' < /srv/backups/SELECTED/platform.dump
docker compose --env-file .env -f compose.yml exec -T postgres sh -c \
  'exec pg_restore -U "$POSTGRES_USER" --clean --if-exists --no-owner -d enterprise_portal' < /srv/backups/SELECTED/enterprise_portal.dump
```

4. 数据库恢复命令会替换目标数据，限新的隔离恢复实例。先用原发布镜像恢复启动并验证登录、授权与附件；如果恢复到新版本，再审查执行 `portal-init init`，完成迁移排练与三件套回归后切 DNS。
5. 从 gateway 重新启动员工会话，确认用户短 ID 与恢复的动态卷吻合。验收后再开放公网入口。

发布前记录所有最终镜像 digest，并用私有 registry 或 `docker save` 保留镜像。基础镜像和 apt 仓库会随时间变更，源码锁文件不是完整供应链冻结；通过后的镜像 digest 是回滚依据。升级前备份、用新 `RELEASE_TAG` 构建并在隔离实例演练。回滚只在数据库向后兼容已确认时切旧镜像；否则先停服务、恢复升级前一致备份和旧镜像，不能只换代码继续使用不兼容新 schema。OpenClaw 更新还要管理已有动态容器的重建；仅 gateway 镜像更新不等于员工运行时已更新。

## 本地离线检查

2026-10-12 OCR 修复：官方 [RapidOCR 1.4.4 元数据](https://pypi.org/project/rapidocr-onnxruntime/1.4.4/)要求 Python <3.13。原 cloud 主锁没有安装该包，故问题是 OCR 依赖缺失；直接加到主 3.13 锁则会安装失败。现在保留业务 3.13，新增独立 3.12 解析环境。当前精确锁中 NumPy 2.5.3 要求 Python >=3.12，结合 RapidOCR 上限，这套依赖采用 3.12；[ONNX Runtime 1.30.0](https://pypi.org/project/onnxruntime/1.30.0/)提供 cp312 的 Linux amd64 CPU wheel，其 manylinux_2_28 基线适用于 bookworm。已逐项查询 19 个精确包版本的 PyPI 元数据及 Linux amd64 wheel，未自动升级依赖。原 wheel 内含三个 ONNX 模型，不需识别时下载。官方 [ONNX Runtime CPU 安装说明](https://onnxruntime.ai/docs/install/#install-onnx-runtime-cpu)对应 `onnxruntime`。

本机独立 `.runtime/company-test/cloud-ocr` Python 3.12.14 安装上述 19 个锁定包且兼容性检查通过；真实合成 PNG/扫描 PDF 均识别出英文、数字和中文，每份返回两个 OCR 内容块；实际识别子进程在调用解析器前可构造未连接的 socket，调用后原 CLI 钩子拒绝三种 Python socket 调用。此结果是 **Windows 本地 OCR**，没有执行 Linux Docker 构建、Linux OCR 或操作系统网络隔离验收。服务器就绪后必须执行上面的冷构建及 `image-checks`。人事简历的扫描 PDF 仍走原 PyMuPDF 提页与模型视觉链路，JD 扫描文件仍拒绝；本地 OCR 修复不代表这些业务策略发生变化。2026-10-11 的历史安装失败和视觉样本证据保留在 `doc/company-department-test-report-20261011.md`。

```sh
python3 -m pip install PyYAML
python3 deploy/cloud/validate_package.py
```

本地检查不访问真实Docker、数据库或外部模型；覆盖 Compose 暴露端口/网络/审批默认值、build路径和COPY输入、MCP/greenlet兼容版本、Python语法、秘密排除与模板弱凭据拒绝。若POSIX shell可用，还对backup.sh执行语法检查，并使用独立mock docker模拟成功、停服务失败、停员工容器失败、数据库备份失败、卷枚举失败与仍有运行员工容器六种状态，核对先关闭入口、错误码、完整标记和仅恢复原运行列表；无shell时明确跳过这一项。这些mock不证明真实Docker卷、数据库恢复或Linux进程行为可用，仍须目标服务器进行一致备份恢复排练。镜像构建和目标Linux smoke 必须另行执行并记录真实结果。
