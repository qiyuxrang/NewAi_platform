# AI-T10：独立中文正向对照

此前Windows沙箱十分钟单元已完成，历史证据不改。本单元由根另行明确授权：仅对其只读确认在库的公开完整名称“中国移动通信集团陕西有限公司”发1次现有应用searxng provider查询；无suffix/换词/换引擎/重试/模型/应用SQL或事实写入。未重复generic或第一家查询，未再安装。

实际命令：`.runtime/company-test/python/Scripts/python.exe scripts/baichuan/probe_searxng_positive_control.py`。脚本复核既有PID11080的创建时间与exe，独立临时Django配置，所有SQL被execute_wrapper拒绝；在原有 `_open` 外仅加同次响应字节捕获，不替换应用解析或再请求。先写独占收据占位，已有收据拒绝隐式重发。HTTPS、代理、Bing引擎配置全部沿用上一单元。

实际HTTP200，1704ms，收到210B JSON。应用来源0，完整中文名称相关来源0，HTTPS/PDF来源0，主要域名为空，`unresponsive_engines=[]`。query SHA256为 `649e35665485a46d77869b4819fed79e8cad92ddb3e5db2241cd76bf4b8cbaa8`，响应SHA256为 `08132f78e82f6f457b924d3a3ab3a8c3039c745c2e79a634e14d08d047cc3259`。0模型、0数据库访问、0事实写入。

私有 `.runtime/baichuan-search-sandbox/positive-control-receipt.json` 保存上述统计；同一响应解析后保存为 `positive-control-response.json`，没有另外请求。离线检查：原始JSON的results也为空，query严格回显完整公司名，answers/corrections/infoboxes/suggestions均为空，未给number_of_results字段或引擎错误。故没有“JSON有结果但应用_source过滤丢光”的证据；Bing原HTML未由既有服务持久保存，无法从这次已收JSON区分真正空结果、挑战页或引擎HTML解析丢项。不能为检查HTML另发请求，也不推定挑战已存在。

离线配置核查仅保留Bing且显式disabled=false；默认 `search.default_lang=auto`，专业类别默认general。先前成功通用请求显式传 `engines=bing&language=en`，现有应用请求只传q/format，因此不是只改变中文名称的完全受控实验，不能据此断言“所有中文检索均不可用”或把原因锁定中文编码/上游。下一个获准对照可先验证默认语言/引擎派发，不应靠反复替换企业名碰运气。上游固定版本实现见 [Windows单元](2026-10-17-searxng-windows-sandbox.md)；本单元没有修改其配置或源码。

结论：这次较强的中文正向对照仍未使**当前应用默认参数的企业发现路径**通过质量门禁，不能扩大1283批次，不能宣称企业不存在或没有资质。SearXNG能运行及通用查询相关的证据继续保留，企业与通用门禁分开。未产生可供本轮pinnedGET的候选URL。owned本机服务PID11080继续保留，精确身份/路径和安全停止命令沿用 `owned-service.json`；未启动自动研究。脚本py_compile和git diff --check实际通过，未重跑无改动业务测试。

## 追加只读：真实函数离线参数追踪

根随后仅授权离线检查，未增加任何HTTP请求。沙箱 `offline_request_trace.py` 直接使用当前固定上游版本的settings_loader、load_engines、Preferences、webadapter及Bing的request函数；不导入会初始化数据库的webapp。在子进程内阻止socket.connect/connect_ex/getaddrinfo与sqlite3.connect；Windows asyncio自身使用的本地socketpair预先建立，仅用于线程自唤醒，无HTTP。favicon选项列表/空插件偏好用无副作用stub替代，其余语义路径使用原函数。最终 forbidden_operation_attempts 为network=0/sql=0，8组构造全部完成，私有 `offline-request-trace.json` 保存结果。

可证实的路径如下：

- 应用product_web_search发q/format，未添加Accept-Language。SearXNG ClientPref在缺少该头时locale=None，webadapter把默认auto变成all；没有依据中文查询内容自动变zh-CN。当前设置仅bing且disabled=false，默认general确实选中bing，不是没有引擎。
- 对两个公开完整企业名称，各运行默认/显式all/en/zh-CN四种参数构造。8组webadapter.query均与输入相等；经Bing request的urlencode、再parse_qs解码，q均完整还原且SHA256严格一致。没有本地编码删词/替词证据。此处构造完成未交curl传输，不能证明远端实际接收或解释一致。
- 当前safe_search=0，8组均生成adlt=off；默认和all只生成q/adlt，en增加setlang=en，zh-CN增加setlang=zh。固定引擎代码对cn/us/ru不生成cc，当前8组均无cc，未自动加mkt。不能把历史RSS的cc/mkt对照当本HTML引擎的实际参数。
- 本地Bing parser仅抽取 `ol#b_results > li.b_algo` 对应标题、链接、段落。若上游给了不含该结构的HTML，即使HTTP200仍可能形成空results；没有该次原HTML无法区分无匹配、结构变化或挑战。当前私有210B JSON只足以排除应用层丢掉原JSON结果，不能排除引擎HTML parser丢项。

固定源码定位：`searx/preferences.py` ClientPref.from_http_request、`searx/webadapter.py` get_search_query_from_webapp、`searx/search/processors/abstract.py` get_params、`searx/engines/bing.py` request/response、`searx/search/processors/online.py` _search_basic/_send_http_request。均位于上一单元固定commit，未改业务/沙箱引擎或运行中服务。

最小下一验证建议（**本单元未执行**）：同一公开正向名称，只增加显式language=zh-CN，其他参数保持；在该唯一请求的引擎HTTP响应到达、HTML parser之前保存有界原HTML与请求URL/响应哈希至私有沙箱，再离线检查完整企业名、b_algo、明确no-results及challenge标记。只保存应用JSON不足以判断上游解析路径。仍禁止浏览器模拟、挑战处理、重定向、重试或全库研究；若需先加观测hook，应仅沙箱、有限大小、无外部上报。owned18888进程按根要求保持不停止。
