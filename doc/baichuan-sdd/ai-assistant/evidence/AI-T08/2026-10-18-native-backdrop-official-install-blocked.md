# AI-AC01：官方Firefox已安装，原生fallback验收受启动故障阻塞

2026-10-18 04:16–04:20（北京时间）。结论：**官方测试浏览器安装PASS；原生CSS能力及冻结CSS机制尚未执行成功，真实业务页面NOT_RUN。** 没有将浏览器启动失败当成前端fallback失败或通过。

## 实际安装与来源

使用现有verification Python/Playwright1.64.0，执行一次 `python -m playwright install firefox`，目标为原用户默认 `%LOCALAPPDATA%/ms-playwright` 测试缓存。安装前缓存不存在、文件清单为空；先写私有install-intent，设置`PLAYWRIGHT_SKIP_BROWSER_GC=1`，未改Edge、系统默认浏览器或服务，未删除用户文件。官方安装器自身每包最多5次尝试、未找到公开禁重试参数；本次三包实际均attempt#1完成，无额外安装器重跑。外层300秒硬限，本次60.572秒、exit0，无超时。

| 官方包 | 版本/修订 | 日志download-complete实际字节 |
| --- | --- | ---: |
| Firefox win64 | 157.0 / 1555 | 129834277 |
| FFmpeg win64 | 1013 | 1663577 |
| Winldd win64 | 1007 | 128684 |
| 合计 | 三包均首次尝试 | 131626538 |

来源为官方CDN：[Firefox](https://cdn.playwright.dev/dbazure/download/playwright/builds/firefox/1555/firefox-win64.zip)、[FFmpeg](https://cdn.playwright.dev/dbazure/download/playwright/builds/ffmpeg/1013/ffmpeg-win64.zip)、[Winldd](https://cdn.playwright.dev/dbazure/download/playwright/builds/winldd/1007/winldd-win64.zip)。保留Node正常TLS验证，未设置不安全TLS选项。实际大小来自官方安装器下载完成日志，不是先前HEAD估算，也不含网络协议开销；安装器删除临时ZIP，未获得ZIP内容SHA。初始install-receipt的“无法观测”字段未覆盖，最终补充收据明确引用日志实测大小。解压后缓存总文件367439751字节。完整CLI、缓存前后列表、来源/字节/尝试日志及exe SHA留私有。

Playwright本机LICENSE为Apache2.0；FFmpeg包实际含`COPYING.LGPLv2.1`；Firefox的两个omni.ja中实际读取并另存原生license.html，保留Mozilla[MPL2.0](https://www.mozilla.org/en-US/MPL/2.0/)及组件条款，不把整个下载bundle归为单一许可。浏览器包内文件和许可未修改。

## 真实失败及零更改定位

按冻结SHA `d034327d22f4dc7cf14a272d80a87daf420c104785940b49077895fae88e66c8` 执行 `native-fixture.py --execute`。Firefox启动即报`BrowserType.launch: spawn UNKNOWN`；未创建page，未运行CSS.supports、未生成截图。一次独立`firefox.exe --version`返回原生WinError14001，并行配置错误。Windows Application/SideBySide事件33明确指出找不到`mozglue,language=*,type=win32,version=1.0.0.0`从属程序集。

只读检查确认：Windows11 build26200/x64、Intel CPU地址及数据宽64；Firefox.exe与mozglue.dll均PE machine0x8664。后者实际存在656896字节。无sidecar manifest；以`LoadLibraryExW(LOAD_LIBRARY_AS_DATAFILE)`只读提取嵌入资源，不执行DllMain：exe资源1包含mozglue依赖、DLL资源2声明mozglue1.0.0.0与文件名，两个manifest原文和SHA已保存。exe assembly自身processorArchitecture为`*`，mozglue依赖及DLL assembly未声明该属性；这只是观测，不擅自判断或修改。application.ini为Firefox157.0/BuildID20261002120333，platform.ini为157.0/20261002123222。两文件Authenticode均NotSigned；没有证据将未签名直接归为本次SideBySide故障原因。

有界检索官方Playwright仓库，仅发现泛化[spawn UNKNOWN旧报告](https://github.com/microsoft/playwright/issues/24557)及[企业安全策略案例](https://github.com/microsoft/playwright/issues/35363)，未找到与本机mozglue事件对应、可明确支持的环境变量/正确executable调用修复。没有采用非官方浏览器、二进制/manifest修改、换目录规避或安全白名单。两个原生pref对照脚本已准备，但同一exe尚不能加载，未做无意义重复启动，故对照为BLOCKED_BEFORE_PAGE，不能声称true/false已测。

## 保护与恢复

163个前端文件重新计算SHA全部匹配，原冻结fixture脚本不变。业务登录0、SQL连接0、模型调用0、服务/前端/核心/源码测试/共享SDD状态修改0；本轮唯一新增软件为上述三个授权测试包。没有浏览器页面，因此没有页面出站请求；未做OS级抓包，不作额外网络证明。真实页面双角色零query验收仍未运行，AI-AC01此格保持未完成。

私有目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/backdrop-native-capability-preparation/`。最终收据`installation-native-final-receipt.json` SHA `7328a07dfe7e16b3ffd2bf9850098b15be98c99379eb72fbde5c3c337f199292`；冻结清单`installation-delivery-manifest.json` SHA `dd54a1cae22b98e0de02ef42e28971203df1db0d269dce5bd1cb8fa324f43d5d`。保留准备证据及本次失败，不覆盖旧记录。下一恢复点是官方157/1555本机loader故障；修复前不进入业务UI验收、不进一步下载或安装组件。
