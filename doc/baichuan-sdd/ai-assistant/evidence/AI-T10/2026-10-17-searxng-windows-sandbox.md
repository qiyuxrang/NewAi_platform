# AI-T10：Windows原生SearXNG有界沙箱

## 实施前合同

起始2026-10-17 11:49:18 UTC，10分钟封顶（11:59:18 UTC结束）。根代理授权先审查Kerberos255/searxng-windows公开实现、许可证、固定版本、Windows补丁、启动器及官方依赖；只在新ignored `.runtime/baichuan-search-sandbox` 使用已有Python3.12，至多一次隔离依赖安装与一次通用公开查询。遇到时限、依赖或来源限制立即保存恢复点，不循环重试。

不执行第三方一键脚本、登录启动任务或自动更新器，不装系统组件，不改全局代理/环境、业务代码、企业库或事实/研究计数；仅loopback绑定，正常TLS，可使用既有本机无凭据代理；禁挑战绕过和公共实例轮换。第三方源码仅保留在沙箱并记commit/hash/许可证，不复制进业务代码。先以最小引擎和JSON接口验证，不将HTTP200或非空结果当企业研究可用。沙箱安装/启动失败不标应用适配已验收。源码审查与实际执行结果续记于下。

## 版本、许可证与实际审查

- Windows工具仓固定commit `97bd2cc06dcc660489b0530f5307d2e848742f86`，部署脚本/文档MIT；其可选API Pool引擎适配另有AGPL标记。只借鉴必要Windows补丁，未运行或复制一键部署/API Pool。[作者仓库](https://github.com/Kerberos255/searxng-windows)、[许可证](https://raw.githubusercontent.com/Kerberos255/searxng-windows/97bd2cc06dcc660489b0530f5307d2e848742f86/LICENSE)。
- 审查install/start/run/注册登录任务代码：原流程会下载移动master、升级依赖、可启API Pool及注册任务；本轮全部不调用。作者启动器把代理地址写日志，本轮自有启动器不输出代理。[安装实现](https://raw.githubusercontent.com/Kerberos255/searxng-windows/97bd2cc06dcc660489b0530f5307d2e848742f86/scripts/install.ps1)、[运行实现](https://raw.githubusercontent.com/Kerberos255/searxng-windows/97bd2cc06dcc660489b0530f5307d2e848742f86/scripts/run.ps1)。
- 上游SearXNG固定 `2a6fc07be3760543c7b6d1d1bfe62f5765d5d9d6`，AGPL-3.0-or-later；下载7222627B，ZIP SHA256 `87c4d81bfa670c9fa74930dac2bafdccfb7266d832e2c27771cc460a60abca40`。源码保留许可证，不进入业务代码；API可复用本项目已有searxng分派。官方依赖已改用curl_cffi/valkey，而非假设旧httpx。[固定setup](https://raw.githubusercontent.com/searxng/searxng/2a6fc07be3760543c7b6d1d1bfe62f5765d5d9d6/setup.py)、[固定requirements](https://raw.githubusercontent.com/searxng/searxng/2a6fc07be3760543c7b6d1d1bfe62f5765d5d9d6/requirements.txt)。
- [Windows补丁](https://raw.githubusercontent.com/Kerberos255/searxng-windows/97bd2cc06dcc660489b0530f5307d2e848742f86/scripts/apply-windows-patch.ps1)仅必要部分：pwd可选导入与异常日志身份fallback，沙箱修改后valkeydb SHA256 `c579f0cdad5bb243446b22902037ac55855feefe6ec57b05fc85276ec3a92c0c`。不复制可选API Pool。已检查源码归档的唯一Apache模板符号链接，安全解压跳过该无关项；不创建指向沙箱外的链接。
- 官方仍以Linux/Unix为支持重点，[官方讨论4029](https://github.com/searxng/searxng/discussions/4029)不保证Windows原生可用。因此本轮以实测判定，不依赖README宣称。

## 实际一次安装、通用查询

现有bundled Python3.12.14新建独立venv；只安装固定requirements的二进制wheel，PyPI标准HTTPS、retries=0、15秒连接限额、150秒子进程限额。**唯一一次依赖安装77.068秒成功**，未升级全局环境、未执行第三方setup脚本；curl_cffi0.16.3、Flask3.1.3、valkey6.1.1，完整列表保存沙箱 `installed-versions.txt`。原始安装收据 `install-attempt.json`。

配置仅保留Bing HTML一个引擎、JSON、127.0.0.1:18888，正常TLS、本机无凭据代理、retries=0、max_redirects=0，无公共实例轮换。沙箱Bing请求明确 `impersonate=none`，未采用curl_cffi默认浏览器TLS模拟；修改后该文件SHA256 `9ed3d5eb8f79481c0b6666bfb5e602739b52fef3a58c57f5393fc06b306a04c5`，仅沙箱内修改。[上游网络实现](https://raw.githubusercontent.com/searxng/searxng/2a6fc07be3760543c7b6d1d1bfe62f5765d5d9d6/searx/network/client.py)。

首启动因本轮误将impersonate放入Network构造配置而TypeError退出，0查询；保留 `first-startup-failure.json/.log`，改在Bing请求参数赋值后第二次启动成功，未再次安装。唯一通用查询 `Python official documentation`：HTTP200，10项，10项标题/摘要含python，4项python.org或docs.python.org，无失败引擎，启动加查询2.245秒。响应SHA256 `9717434439ac07fa09832a3de1b0a75af1fbb48dfef8de3c1e5ba1c416d8157b`；`generic-search-receipt.json`。该临时进程PID27616已停止。

一次ACL收紧误用继承标记使子文件缺有效ACE，随后全树纠正为与既有private_json一致的当前用户直接FullControl，继承保持关闭，无Everyone/Users授权；root已实际复读安装/通用收据成功。服务密钥/代理仅在私有沙箱配置，不输出。完整性/语法检查不等于搜索质量验收。

## 根追加授权：既有应用provider的两次企业对照

通用成功后根显式追加最多2次已公开企业名查询，仍0模型、0应用SQL/事实写入。新增自有诊断 `scripts/baichuan/probe_searxng_company.py`；先保留一次请求占位收据，防止中断隐式重发。真实使用现有 `search_public_query` → searxng provider，独立Django配置SQL execute_wrapper拒绝所有SQL；最多6来源，不修改共享搜索代码。

1. 原公开全称+“官网 联系方式 公开资质”：完成，应用结果0，1986ms；query SHA256 `e6b8e815f5a2f8fe6be3c349624a4ca66ece39ca167fcf445b6db00707f7117e`，与原RSS缓存查询一致。收据 `company-app-search-receipt.json`。
2. 单独公开完整企业名、无suffix：完成，应用结果0，822ms；query SHA256 `500da50b56cdd80851705c61ee23234620b099f4a36d66bf4b4dc68eff98bf1f`。收据 `company-app-bare-name-receipt.json`。

两次title/text完整名称命中均0、HTTPS/PDF候选均0。应用空来源集合SHA256均 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`。不是企业不存在的证据；根已用另一检索工具找到历史政府名单PDF，尚不能当当前主体/资质核验。**Windows原生运行和通用相关性通过，本机该单引擎企业检索相关性未通过；不扩全库。** 不继续替换词、换引擎或重发查询。

## 恢复与移交

根要求保留新owned服务以便接管：PID **11080**，identity=`baichuan-owned-searxng-sandbox-v1`，creation FILETIME `134367118368644169`，仅 `127.0.0.1:18888`。命令为沙箱 `venv/Scripts/python.exe -m searx.webapp`，cwd固定下载源码目录。完整进程路径、命令、创建时间和stop命令在私有 `owned-service.json`；启动过程清理所有业务/网关秘密，只传入系统运行必需变量和沙箱settings/TEMP/PYTHONPATH。没有注册启动任务。

停止命令：`.runtime/company-test/python/Scripts/python.exe scripts/baichuan/probe_searxng_company.py --stop`。其用Windows进程句柄同时核对PID、创建FILETIME与exe后才终止同一句柄，拒绝PID复用；不批量杀Python。默认入口与 `--bare-name` 都有既有收据拒绝隐式重发；不得把它当生产自动启动器或自动研究队列。下一步如需其它引擎/查询必须由根另立有界单元，不重装本venv、不更改真实研究coverage。沙箱有状态与证据可恢复，按10分钟合同结束本单元。
