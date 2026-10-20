# 另一台 Windows 电脑更新与本地启动

统一交付分支：`main`。本次将百川完整业务与架构、权限、恢复改进合入主分支；检查范围见[整合检查记录](merge-newai-20261020.md)。历史交付分支保留，但后续更新使用主分支。

本说明覆盖两种情况：另一台电脑已能运行本项目时更新现有环境；没有百川本地库时，从公开快照显式建立新空库。**代码和企业快照可以从 GitHub 取得；账号、模型密钥、历史业务附件、已安装运行时和依赖不在公开仓库中。首次克隆需要安装和私有配置，不承诺免配置运行。**

## 1. 更新代码（保留另一台电脑已有资料）

在另一台电脑的项目根目录打开 PowerShell。下列 `origin` 必须指向 `https://github.com/qiyuxrang/NewAi_platform.git`；如果像本机一样将该仓库命名为 `newai`，请把命令里的 `origin` 换成 `newai`，不要误更新上游 MultiUserClaw：

```powershell
git status --short
git remote get-url origin
git fetch origin main
git switch main
git merge --ff-only origin/main
git log -2 --oneline
```

先保存该电脑未提交的工作；有冲突时不要执行 reset --hard、clean 或删除数据库。若本地没有 main，执行 `git switch --track -c main origin/main`（仓库远端叫 newai 时相应替换）。已有 main 分叉时，`--ff-only` 会停止并保留双方改动，先整合本机修改再更新。

首次克隆：

```powershell
git clone --branch main --single-branch https://github.com/qiyuxrang/NewAi_platform.git
cd NewAi_platform
```

## 2. 验证企业数据完整性

已有 Python 3.11+ 即可执行，不写数据库、不联网、不调用模型：

```powershell
python scripts/baichuan/export_repository_data.py --verify data/baichuan
```

本次快照应返回 `PASS`、9 表、25,843 条、1,283 企业、4,064 来源路径、1,754 去重归档。包括 1,460 条旧资质、1,622 条证书/观察；原人工字段、版本、证据和核实状态保留。不是“所有企业信息都补齐”。JSONL/CSV/原 Excel/来源归档均在 `data/baichuan`。

## 3. 已有运行环境的电脑

原本使用百川专用入口 `13180` 的电脑，保留其 `.runtime/baichuan-ai-local` 和 `.runtime/company-trial/model.env`。更新后先停止该电脑所属旧服务，再启动，使后端加载新代码；只在目标电脑执行：

```powershell
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_dev.py stop
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_dev.py start
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_dev.py status
```

入口：<http://127.0.0.1:13180/departments/product/baichuan>。该环境已有企业时，**不要执行下面的新空库恢复**；恢复工具会拒绝覆盖。已有账号和密码保留，凭据文件为该电脑自己的 `.runtime/baichuan-ai-local/accounts.json`。

原本使用企业整合入口 `3080` 的电脑，继续使用 `启动项目.cmd` / `停止项目.cmd`，需要保留该电脑自己的 `.env`、业务 `.runtime`、Docker 数据卷及 Office 环境。三件套新策略随本轮代码提供，加载对应业务后端/worker 后生效；百川 `local_dev` 启动器只管理百川环境，不启动完整产品/人事/工程 worker。不要用两套入口指向同一库或复制旧进程 PID 记录。

**3080 入口另有版本条件**：它使用本机 ignored 的 `frontend/dist` 和 `manage_front/.next`，git pull 不会更新这些产物；目标电脑若仍是旧构建，需要在那里按原整合环境流程重新安装/构建对应产物。业务库也要先备份并检查是否有待执行的增量迁移，不能用公开企业快照替换它。可先运行 `启动项目.cmd -CheckOnly` 检查已有运行时、配置与构建文件；该检查不等于迁移和新构建已经完成。本轮没有操作该电脑的企业环境或构建前端，因此不能保证所有旧环境只拉取后双击就适配。13180 专用入口按现有源码运行，不依赖上述生产构建产物。

## 4. 没有百川环境的新电脑：首次准备

安装 64 位 Python 3.13、Node.js 24 LTS 和 Git，并在新克隆目录执行：

```powershell
py -3.13 -m venv .runtime/company-test/python
& '.runtime/company-test/python/Scripts/python.exe' -m pip install -r scripts/baichuan/requirements-local.txt
npm --prefix frontend ci
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_dev.py migrate
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/restore_repository_data.py
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/restore_repository_data.py --execute --actor baichuan-dev-product
```

`migrate` 仅初始化带所有权标记的专用本地库和新账号，不启动服务。恢复工具先逐文件校验完整快照、确认 9 张资料表全空且 schema 相符，再用 SQLite Backup API 备份、在单一事务中导入并逐行回读、验证外键。已有企业、资质、证书、规则或证据均会使其拒绝导入，不做全库合并、更新或清空。

导入保留企业与资料 ID、业务字段、时间、核实状态和来源；只将外部审计用户引用显式映射到 `--actor` 指定的新本地操作员，原用户 ID 保留在不可变 JSONL 和映射收据中。所需研究任务引用建立为 **cancelled 归档占位**，不会继续补全、访问网站或调用模型。来源正文仍保存在仓库压缩归档中；历史本机绝对路径不是新电脑上的可执行文件路径。完整历史用户、会话、对话、附件及任务执行状态不包含在此数据快照中。

导入备份与收据：`.runtime/baichuan-ai-local/repository-imports/<新编号>/`。导入成功后再次执行会明确拒绝，不重复写入。若进程恰在事务提交后、来源状态收据写入前中断，资料保留，重复导入仍拒绝；先核对备份收据和现有资料再人工恢复状态，不清库重来。

文本型 PDF/DOCX 等文件解析及扫描 OCR 使用独立 Python 3.12 环境（不装时不能宣称文件/OCR完整可用）：

```powershell
py -3.12 -m venv .runtime/company-test/cloud-ocr
& '.runtime/company-test/cloud-ocr/Scripts/python.exe' -m pip install -r services/business/backend/portal/source_parsers/requirements.txt
```

复杂白话/文件理解需要自己的模型配置。通过私有方式将已有配置放到 `.runtime/company-trial/model.env`，不要发到 GitHub；字段见下一节。配置后运行下面命令。它们仅注册专用本地模型路由；`probe` 会实际调用一次模型，不是免费健康检查。无需搜索服务，日常查询不自动补全。

```powershell
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_model.py configure
# configure 后先启动所属模型网关，随后才可通过原权限链探测。
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_dev.py start
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_model.py probe
& '.runtime/company-test/python/Scripts/python.exe' scripts/baichuan/local_model.py activate
```

`configure/probe/activate` 是既有单次初始连接流程，并不限制日后查询总调用数。已有模型连通环境不要重复执行 configure/probe；直接启动保留原配置。基础健康检查不调用模型。上述新电脑真实模型探测本轮未执行。

## 5. 必须私下保留的配置

模型文件格式（下面只是字段示例，不含可用密钥）：

```dotenv
MODEL_BASE_URL=https://your-provider.example/v1
MODEL_NAME=your-existing-model
PORTAL_MODEL_KEY_PRIMARY=replace-locally
MODEL_SUPPORTS_VISION=0
MODEL_MAX_OUTPUT_TOKENS=4096
MODEL_TIMEOUT_SECONDS=120
```

不要把本机完整 `.runtime` 公开上传，也不要直接搬运虚拟环境、浏览器登录态或旧 PID 文件冒充换机安装。已有企业整合环境的其他私有业务库/文件与 Docker 卷需要单独备份迁移，见[本地运维说明](baichuan-sdd/ai-assistant/local-operations.md)；GitHub 企业快照不是整机运行环境恢复包。

本轮换机核对的实际结果另见[换机验收记录](github-local-update-receipt.json)。本机隔离克隆/导入验证不等同于已经在用户另一台电脑执行；目标电脑系统、网络、依赖安装、Office、模型权限及私有配置应在那里复核。
