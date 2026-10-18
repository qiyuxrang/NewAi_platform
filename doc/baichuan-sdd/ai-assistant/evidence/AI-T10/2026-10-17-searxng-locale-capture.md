# AI-T10：显式中文locale与同次HTML捕获

## 实施前合同

根另行授权独立5分钟单元：同一公开正向名称“中国移动通信集团陕西有限公司”、同Bing引擎，仅在现有应用Request边界添加固定language=zh-CN，实际最多1次请求，不重发。开始前保存私有独占预算占位；仅对所属18888沙箱安全停止/重启，更新PID/创建时间。其余5业务服务、企业库、引擎、代理、TLS、safesearch不改。

最小沙箱capture补丁在引擎HTTP接收后、HTML解析前保存该唯一响应最多512KiB，超限明确截断。最终URL仅保存固定host和SHA256、实际q哈希，不保存含秘密URL。捕获仅精确目标查询，独占文件防重复；不增加网络请求、不解决挑战或模拟浏览器、不重试。0模型、0SQL、0事实/coverage写入。随后对同次私有响应离线检查b_algo/no-results/challenge和全名匹配，失败也保存恢复点，不扩大研究批次。本节先落盘，再执行。

开始12:05:20 UTC，截止12:10:20 UTC。源码采用上一单元固定版本、同一Bing HTML引擎。页面/前端按用户新约束冻结，本单元无任何前端改动。

## 首次失败及根明确追加预算

首次capture补丁语法内存检查成功，但写文件漏指定UTF-8，Windows默认编码使新引擎模块中文常量无法按UTF-8导入，PID15784启动SyntaxError退出。原服务终止和新启动的监听竞态使本地探测误认就绪，唯一应用请求以 `web_search_unavailable` 失败，无HTML捕获。私有 `locale-capture-receipt.json` 与 `locale-server.log` 保留原失败，不改成通过；不凭猜测把实际上游次数报为已证明0。

根收到明确失败原因后另行授权一次追加请求：同企业、同language=zh-CN、总本地尝试2，仍在原5分钟内。修正脚本显式UTF-8、保留首收据，新增独占 `locale-capture-attempt2-receipt.json`；先确认18888无原监听，成功启动同配置服务，再执行第二次。未安装/换引擎/变代理/TLS/safesearch/开自动研究，未隐藏重试。

## 实际第二次结果与离线HTML分析

第二次真实应用请求成功，HTTP200、原JSON10条、应用返回6条、总5803ms。候选均HTTPS，PDF0；域名为中文Wikipedia两条、百度百科两条、BBC、gov.cn。**应用6条及原JSON全部10条的title/content中完整企业名均未命中。**

沙箱 `online.py` 在 `_send_http_request` 返回后、`engine.response` 前对精确目标名称做一次独占capture；实际HTML125080B，完整保存，未触及512KiB上限。SHA256 `8eff4add71ebf4cdceb87c4cd810f56dee1484ef418da0b52380350bec52b995`。request/final host均www.bing.com，URL哈希相同 `d4d1b87413aa22a97fd7a8b598829c61f30a073b8058ba44c0de4f02be080a3a`；实际q SHA256 `649e35665485a46d77869b4819fed79e8cad92ddb3e5db2241cd76bf4b8cbaa8`，与公开完整企业名严格一致。上游参数q/adlt/setlang，setlang=zh、adlt=off；无重定向/自动重试或浏览器TLS模拟。

对同次文件离线使用实际DOM抽取：10个b_algo，与原JSON10项一致；这些结果正文中完整企业名、“中国移动”、“陕西”、“移动通信”均0，原JSON标题/摘要对应指标也均0。整个HTML有6次完整名称，但位于查询回显而非结果正文，不能当相关性证据。未发现本轮检查的captcha/recaptcha/verify-human/challenge-form或明确no-results短语；只说明所查标记未出现，不能保证所有限制均已排除。

因此显式中文locale使当前路径产生了结果，却未取得企业相关候选；未发现本地编码丢词、选错引擎、应用parser丢光，或HTML缺b_algo的证据。更接近上游把查询放宽成泛结果的现象，但没有其内部行为证据，不能确认具体降级策略或归责代理。不得因gov.cn域名便视为该公司的证据，不得宣称企业不存在或没有资质；本次仍不能开放1283批次。

## 私有证据与移交

本轮原始资料仅在ignored沙箱：`locale-upstream.html`、`locale-upstream-metadata.json`、`locale-attempt2-app-response.json`、`locale-attempt2-app-sources.json`、`locale-offline-analysis.json`。仅收据统计写本证据，不把网页正文、服务密钥或代理地址带进共享文档。最终沙箱capture模块SHA256 `4fda21d9ab09aaa685b0eccb045477f01bb133a7b9c0b57b17f138a0e8f7e494`；capture独占文件已消耗，不可将保留服务当自动批量研究入口。

所属服务已恢复并按根要求保留：PID **10076**，creation FILETIME **134367124732644516**，identity=`baichuan-owned-searxng-sandbox-v1`，仅127.0.0.1:18888。`owned-service.json` 已更新exe/命令/cwd/创建时间，原PID11080与失败PID15784均不再使用。停止仍为 `.runtime/company-test/python/Scripts/python.exe scripts/baichuan/probe_searxng_company.py --stop`，核验同进程句柄身份后终止。五业务服务未重启，0模型/SQL/事实/研究计数写入。相关脚本py_compile实际通过；未重复搜索或未变更业务回归。后续只可由根另立有界验证，不把本次6条非相关URL送正文抓取以消耗预算。

### 最终停止回执（取代上段临时保留状态）

根随后明确要求停止所属服务。12:09:58 UTC前实际执行上述stop helper：同一Windows句柄核对PID10076、creation FILETIME和exe后终止，返回stopped_owned_pid=10076；随后Get-NetTCPConnection确认18888无Listen。私有 `owned-stop-receipt.json` 保存身份与无监听结果。沙箱源码、venv、所有原始响应/安装及失败收据均保留，无删除。自12:05:20开始至实际停止不到5分钟，未延长网络单元。最后四个新增诊断脚本py_compile、git diff --check实际通过，SDD结构校验另行记录；不修改共享任务/进度/检查点。
