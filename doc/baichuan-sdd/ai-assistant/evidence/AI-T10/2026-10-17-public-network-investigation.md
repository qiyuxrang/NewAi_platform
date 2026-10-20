# AI-T10 本机公开网络与无密钥搜索有限调查

日期：2026-10-17；共享工作区，基线 HEAD `ef1676cd8327d693dab897c45a234ba91413884e`。本单元不访问企业数据库，不调用模型、不发送企业名称/源表/内部需求，不修改事实、研究清单或 coverage。初始调查保留原业务代码；随后经新授权实施独立RSS适配器（见末节），共享进度文件未修改。

## 实测结论

通用 HTTPS 当前可用，旧的 `self-signed certificate in certificate chain` 记录不能泛化为所有网页失败。实际应用 `fetch_public_page` 经既有公网 DNS 校验、固定 IP 的 TLS socket 与主机名验证成功读取 `https://example.org/`：173字符，849ms，正文 SHA256 `51123be1fcfbaaf0e735569109be1c031cab9d4d96d88ea7bdf7557a56cccc0c`。执行期间数据库 execute_wrapper 禁止全部 SQL，未创建配置的临时 SQLite 文件。

现有应用搜索仍为 Tavily/Brave/SearXNG 三个适配器，尚未配置可用 provider。单个公开 Bing RSS 通用查询真实返回10条公开链接，是可继续研究的无密钥候选；本轮未自动启用。不能将 DuckDuckGo 的挑战响应推论为所有无密钥搜索不可用。

应用进程实际外发共 **8次**，均为固定公开页面或 `Python official documentation` 这个通用查询，没有隐式重试：

| 次数 | 固定目标与方式 | 实际结果 | 限制与解释 |
| --- | --- | --- | --- |
| 1 | example.org，原生 OpenSSL，直连 | HTTP200，577B，595ms，含 Example Domain | TLS验证开启 |
| 2 | example.org，truststore Windows CryptoAPI，直连 | HTTP200，577B，565ms，含 Example Domain | TLS验证开启，未注入全局 ssl |
| 3 | Python官方 ssl 文档，原生 OpenSSL，直连 | HTTP200，读262145B，572ms | 达到诊断读取上限后关闭，不声称全文抓取；该探针不是正文适配器 |
| 4 | DuckDuckGo HTML 通用查询，直连 | URLError，8024ms | 8秒连接预算后失败；没有保存异常原文或重试 |
| 5 | 同一 DuckDuckGo 查询，既有系统代理 | HTTP202，14274B，1704ms，challenge=true，结果链接0 | 不解验证码，不变换身份/实例绕过 |
| 6 | example.org，实际应用 pinned public fetch | 成功，173字符，849ms | 无SQL/模型；应用原有SSRF和TLS边界 |
| 7 | Bing公开RSS通用查询，既有系统代理 | HTTP200，5001B，1471ms，合法RSS10项/10个HTTP(S)链接，challenge=false | 单次8秒预算，无账号/密钥；仅证明此时此查询可取得候选 |
| 8 | 百度公开HTML通用查询，既有系统代理 | HTTP302，217ms | NoRedirect停止，不跟跳/重试，不推断其目标一定是验证码 |

Bing响应SHA256 `c944c7f75d833e6e0a4cd469a73a2ae241a3ce8ec549d7fbf0936d0f2f02581f`。通用Python文档的有界响应SHA256 `2bdef83fa822da83a6f9a173c7e2627c5b56d860c1ff86cb5343ce20ff3faa83`。没有保存网页原文、搜索结果列表、代理地址或任何凭据。文档研究使用外部浏览工具访问公开官方资料，未将其冒充应用搜索成功。

## 现有边界与本机环境

- `product_web_search._provider_search` 的请求目标由固定 provider 构造；10秒连接/20秒总时限、262144B、最多6条结果、摘要只作线索。它复用 `product_knowledge_service._open`，明确 `ProxyHandler({})`，不继承系统代理，且不跟随跳转。
- `product_assistant_tools.fetch_public_page` 仅接受公开 HTTPS/443，复用 `model_gateway.transport._resolve` 的全部 DNS 地址公网校验，使用 `_PinnedHTTPSConnection` 固定已验证地址，SNI/证书主机名仍为原域；20秒、512KiB、拒绝跳转，输出最多10000字符。
- 本机存在注册表系统代理，HTTP/HTTPS代理均为本机地址且没有内嵌凭据；本轮只记录这些布尔事实，不输出地址/端口。诊断代理仅用于固定公开搜索目标；没有把代理注入应用或绕过正文 DNS 固定。
- Python3.13.16、OpenSSL3.5.9（2026-09-29）、truststore0.10.4、certifi2026.7.22、httpx0.28.1。默认SSL context含54个CA；Windows ROOT库55条、CA库20条。truststore已经在本机和云requirements.lock中存在，无安装操作。
- Docker及uv未找到可执行程序；wsl.exe存在，但 `--list --quiet` 返回1及需安装WSL的提示。本轮未安装WSL/Docker或系统组件，也未持续试公共SearXNG实例。

当前无证据要求改变通用TLS配置。对特定站点链错误，应先确认该站点完整链与本机受管理信任，而不是关闭证书验证、任意信任抓回的证书或加默认不安全回退。

## 官方依据、版本、许可与采用判断

1. [Truststore官方文档](https://truststore.readthedocs.io/en/stable/)：调查时文档0.10.5，本机实际0.10.4；MIT。支持Windows CryptoAPI、获取缺少的中间证书与系统撤销检查；库应显式使用 `truststore.SSLContext`，不在导入时全局注入。本轮仅比较能力，两种context都成功；没有假称已修复旧站点链错误，也未引入业务依赖/代码。
2. [SearXNG官方Search API](https://docs.searxng.org/dev/search_api.html)：调查时 `2026.10.17+2a6fc07be`；GET/POST `/search`、`format=json`需实例启用，许多公共实例禁用JSON；查询会传给外部搜索引擎。[官方源码及许可](https://github.com/searxng/searxng)为AGPL-3.0，setup声明AGPL-3.0-or-later。既有HTTP JSON适配器可复用，不复制其代码。
3. [官方无Docker逐步安装](https://docs.searxng.org/admin/installation-searxng.html)提供Linux包、venv、源码、配置和uWSGI路径；[开发quickstart](https://docs.searxng.org/dev/quickstart.html)还提供纯Python `searxng-run`。[Granian说明](https://docs.searxng.org/admin/installation-granian.html)指出目前其官方支持部署仅在容器；所以不能把Granian/Windows视为已验证部署。当前官方 [requirements](https://raw.githubusercontent.com/searxng/searxng/master/requirements.txt) 与 [网络实现](https://raw.githubusercontent.com/searxng/searxng/master/searx/network/client.py) 已使用curl_cffi/valkey，不能照搬旧httpx教程。Windows原生源码启动属于待隔离验证的开发路径，生产标准安装仍以官方Linux部署为依据。
4. [SearXNG官方DuckDuckGo源码](https://raw.githubusercontent.com/searxng/searxng/master/searx/engines/duckduckgo.py)明确HTML表单协议来自逆向并可能随反机器人逻辑变化，AGPL-3.0-or-later；本轮不复制此实现、不模拟挑战绕过，实际202无结果即不可用。
5. [Bing官方RSS说明](https://blogs.bing.com/search/2005/1/RSS-Feeds-for-Search-Results/)历史明确介绍搜索URL的 `format=rss`。版本是公开HTTP/RSS端点而非有SLA的现行付费API；该历史说明及本次200不构成企业批量自动化可用性/结果许可的保证。没有复制第三方实现或引入许可证；仅按公开接口做一次普通通用查询，后续适配应保留来源并先验证适用约束。

## 实际可接续路径

优先对已成功的Bing RSS做独立provider开发验证：固定HTTPS目标、显式受控代理配置、TLS验证、NoRedirect、严格RSS结构与URL验证、大小/时间/次数/速率上限，映射成现有 `search_snippet` 来源协议。默认关闭，遇挑战/429/跳转即失败，不用空列表冒充已覆盖。其结果只提供候选URL，正文仍走既有防SSRF pinned fetch，不能把搜索摘要升为已核实事实。

SearXNG可作为另一条可部署路径：在获准本机Linux运行时或已有获准Linux服务中按官方源码venv部署，bind loopback，启用JSON/有限引擎、限速/缓存和合法TLS/代理，接入既有searxng provider。无需Docker/新搜索账号，但上游引擎网络与限流仍必须用通用查询实测；当前尚未装好，不标可用。不会通过随机公共实例轮换解决挑战。

本轮按限定8次应用探测结束；未再外发企业查询、启动研究批次、安装组件或修改运行中服务。根代理维护进度/检查点，研究coverage不因这些公开能力探测增加。

## 可复查探针与检查

后续单元执行契约（实现前记录）：仅为显式开启的本地开发环境增加 `bing_rss` provider；固定Bing HTTPS搜索端点，独立loopback且无凭据的系统代理开关，保留标准TLS/NoRedirect，拒绝DTD/实体/超限XML、私网/特殊地址链接；保留既有搜索来源schema/权限和研究来源预算，不写verified facts。先合成回归，最后增加且仅增加1次应用adapter通用查询实测。上述8次属于调查阶段，不冒充新adapter验收；不启动企业查询或全库研究。本机私有RSS消费不建立搜索引擎、镜像或索引，默认禁用，来源仍为discovery。

新增 `scripts/baichuan/probe_public_network.py`，默认无外发；仅固定公开目标，无任意URL/查询入口，不输出完整异常。复查会产生新的外发请求，应显式选择所需项，本轮没有为凑结果重复执行。

```powershell
& .runtime/company-test/python/Scripts/python.exe scripts/baichuan/probe_public_network.py --public-fetch
# 上述实际执行：成功，173字符，849ms，未访问数据库。
# 可选、未重复运行：--tls-compare（2次） --public-search（最多2次）
# 本轮另实际执行：--other-public-search（Bing、百度各1次）
```

初始调查仅新增诊断脚本与本证据，未因此重跑无关CRUD/迁移/全库研究测试。后续适配器检查见下。

## 后续有界RSS适配器：已实施并实测

主任务追加授权后，按上述先记录的契约实现 `portal/product_bing_rss.py`，在既有 `product_web_search.configuration/_provider_search` 分派；新增两个默认关闭配置。未改共享 `_open`、SearXNG URL校验、公开页DNS固定/TLS连接或研究事实服务，不引入依赖或复制第三方代码。

- 仅 `DEBUG=True`、总搜索开关及独立 `PRODUCT_WEB_SEARCH_BING_RSS_ENABLED=True` 时可用；固定 `https://www.bing.com/search` /443 /GET，不提供任意服务URL参数。默认不启用系统代理。
- 独立 `PRODUCT_WEB_SEARCH_BING_RSS_SYSTEM_PROXY=True` 时只接受本机HTTP代理，无用户名/密码、路径/查询/片段，localhost转换为127.0.0.1；只为该固定Bing HTTPS目标设置代理。保留标准 `CERT_REQUIRED` 和主机名验证，拒绝跳转，无重试、挑战处理或实例轮换。
- 单连接8秒、响应总预算20秒前后检查、262144B、50个RSS item扫描上限、最多6个唯一结果、2048节点/12层XML限额；UTF-8，解析前拒绝NUL/DTD/实体声明，拒绝压缩、HTML挑战、非法/重复字段。每进程新请求间隔至少1秒，不等待或自动重试；不能冒充跨进程分布式限流。
- 结果链接仅HTTP/HTTPS标准端口且无凭据/控制字符；复用gateway `_resolve` 对全部DNS地址做公网校验和有界解析。同轮同主机校验缓存；稍后正文仍独立重新解析并固定连接，不能把搜索时的DNS结果当授权。
- 保留既有来源id/query_hash/日期/schema，新增 `discovery_only=true`、`provider_stability=experimental_rss`；`untrusted/reference_only=true`、`source_trust=UNKNOWN`，无摘要时标 `search_title`。不创建“已核实”事实；原研究任务在请求前消费持久source预算，权限与租约边界保持原机制。
- 官方历史RSS说明把接口标为实验，并要求RSS消费而非重建搜索引擎；本单元仅私有本地发现引用，不建立搜索索引、镜像或公开搜索服务，不能宣称现行有SLA的API或不受限批量使用许可。

实际回归：

```powershell
& .runtime/company-test/python/Scripts/python.exe doc/baichuan-sdd/ai-assistant/evidence/AI-T02/probe_capabilities.py --public-search-tests
```

**51 tests / 8.351s / OK，零skip**。包括新RSS14项（13安全边界+1真实持久研究预算）、既有product_web_search22项、研究runtime15项。临时SQLite迁移到0046并销毁；未读取实际企业库。覆盖成功来源schema/限数去重、DTD/实体/UTF16/深度/大小、私网/映射地址/混合公网内网DNS、凭据/端口/协议、代理独立开关与禁止凭据、标准TLS与NoRedirect、302/429/超时、每秒限流、总时间预算，以及source预算耗尽时真实任务先失败且零外发/零证据写入。既有provider、公开词限制、撤权、研究缓存/事实保守性也通过。

随后且仅随后新增 **1次** 真实新adapter通用查询（调查8次之外的第9次；后续无重试）：

```powershell
& .runtime/company-test/python/Scripts/python.exe scripts/baichuan/probe_public_network.py --bing-adapter
```

实际 `success=true`，6条结果，1427ms；标准TLS、本机无凭据代理和实际公网DNS校验；全部来源保持 `UNKNOWN/discovery_only`。source集合SHA256 `d5815c0fb686d9c10617f0180f939019c7c17d70f0e760548ef5f84bb9a64d07`。真实调用期间禁全部SQL、未创建临时DB；模型/企业查询0。未打印或保存结果原文列表。由本次实际stdout保存的私有能力收据为 `.runtime/baichuan-ai-local/bing-rss-capability.json`（限制ACL），保存收据额外外发0次，供后续有界pilot能力门禁引用；不是未来可用性承诺。

`py_compile`（adapter/dispatch/settings/test/probe）及 `git diff --check` 实际通过。当前运行中服务未自动启用provider、未重启、未开始企业研究；根任务可在独立有界脚本中显式临时启用以下设置，保持事实写入关闭和来源预算。

配置键（Django名；对应环境变量加 `PORTAL_` 前缀）：`PRODUCT_WEB_SEARCH_ENABLED=True`、`PRODUCT_WEB_SEARCH_PROVIDER=bing_rss`、`PRODUCT_WEB_SEARCH_BING_RSS_ENABLED=True`、`PRODUCT_WEB_SEARCH_BING_RSS_SYSTEM_PROXY=True`；仍需DEBUG。不开启 `BAICHUAN_RESEARCH_ENABLED`，也不修改 `BAICHUAN_FACT_WRITE_ENABLED`。因此适配器实测完成不等于全库研究覆盖或字段核实增加。

## 最终调用兼容与部署复核

local_start只读复核发现两处真实边界，未用新网络请求复测：

1. owned portal/worker原环境没有固定仓库 `services/business` 模块路径，探针却预先配置了它。因此上述真实请求证明适配器在所需模块路径存在时可用，不能直接证明原运行中服务已可用。正文fetch也依赖相同gateway模块。由local_start负责在owned服务环境增加固定仓路径并做无SQL/外网import smoke；不复制或放宽DNS安全实现，本单元证据应结合其实际检查结果。
2. 既有专业引用入口支持最多3条已许可查询；快速响应后第二条会触发RSS每进程1秒限制并使整批结果丢弃。现为RSS明确仅执行第一条查询，返回来源附 `query_limited`、`query_count_requested`、`query_count_executed=1`，所有输入仍先完整通过许可词校验。其它provider仍执行原来的最多3条；单一用户查询入口不受此改动影响。无等待、自动重试或额外请求。

新增2项合成回归分别检查快速首响应仍只调用一次并保留来源/截断标记，以及未执行的第二条包含不允许内容时仍在网络前拒绝。按原命令再次实际运行：**53 tests / 9.282s / OK，零skip**（RSS16、既有搜索22、研究runtime15）。临时SQLite销毁，实际库/网络调用0。本次最终变更未修改真实请求路径，未为更新收据重发请求。

私有收据保留原有真实调用时间、6条/1427ms和source hash，同时补兼容门禁 `public_dns_validated=true`，并记录最新合成测试53项/9.282s；含 `runtime_import_requires_fixed_repository_path=true` 以避免把探针路径配置误认运行中服务部署验收。root可结合local_start的owned路径修复检查解除部署阻塞。
