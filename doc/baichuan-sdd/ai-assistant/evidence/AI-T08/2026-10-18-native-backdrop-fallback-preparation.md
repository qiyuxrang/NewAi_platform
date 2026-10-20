# AI-AC01：原生无backdrop-filter环境准备（未作页面验收）

2026-10-18。本轮只读盘点及官方来源研究，未安装软件、未登录业务、未访问业务页面或SQLite、未调用模型、未修改核心/测试/前端/服务。163个前端指纹逐份重核一致。已有冻结CSS在 `BaichuanAssistant.css:9` 包含不支持backdrop-filter时采用不透明`#f6faff`背景的原生`@supports not`分支。

## 实际环境与可行方案

本机存在Edge155.0.4283.45；标准ProgramFiles位置无Firefox。已有Playwright Python1.64.0，其驱动包标示1.64.0-beta-1791568591000，registry要求Chromium1248(156.0.8078.4)、Firefox1555(157.0)、WebKit2370(27.2)，三者期望executable均不存在。实际执行 `python -m playwright install firefox --dry-run` 退出0，仅列出下载及安装位置，不下载包；该Python的BrowserType.launch实际签名含`firefox_user_prefs`。

Mozilla当前主线保留`layout.css.backdrop-filter.enabled`原生pref，默认为true；`nsCSSProps::RecomputeEnabledState`根据pref更新属性启用状态，并与图形能力相与。官方属性测试数据库亦按此pref加入backdrop-filter测试。已有旧gecko-dev属性定义明确绑定该pref。故**推荐下载官方Playwright Firefox后用启动pref=false进行真实引擎试验**，这仍是源码依据的可行推断，不能当作Firefox157实测成功。[当前pref](https://raw.githubusercontent.com/mozilla-firefox/firefox/main/modules/libpref/init/StaticPrefList.yaml)、[当前启用逻辑](https://raw.githubusercontent.com/mozilla-firefox/firefox/main/layout/style/nsCSSProps.cpp)、[当前官方属性测试](https://raw.githubusercontent.com/mozilla-firefox/firefox/main/layout/style/test/property_database.js)、[旧属性定义](https://raw.githubusercontent.com/mozilla/gecko-dev/master/servo/components/style/properties/longhands/effects.mako.rs)。当前main及旧master不是该下载包的精确源码提交，包内版本与实际能力仍需实测。

Chromium当前主线backdrop-filter属性定义没有runtime_flag；结合此前Edge实测旧`--disable-blink-features=CSSBackdropFilter`未让CSS.supports变false，不再将旧参数当成能力关闭保证，也未重复同一失效试验。[Chromium当前属性定义](https://chromium.googlesource.com/chromium/src/+/main/third_party/blink/renderer/core/css/css_properties.json5)。该源码BSD-style许可；本轮只研究、不复制到产品。[Playwright官方Firefox用户pref参数](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-option-firefox-user-prefs)说明可以原生传pref，Playwright本机LICENSE为Apache2.0；Firefox相关Mozilla源码为[MPL2.0](https://www.mozilla.org/en-US/MPL/2.0/)。浏览器及附带组件仍须保留各自包内许可/NOTICE，不将整个bundle一概视作Apache2.0。

## 官方包元数据（仅HEAD）

04:09:59左右对registry给出的三个官方CDN URL执行正常TLS HEAD，均307至Microsoft官方Playwright下载域、最终200、未读取包body：

| 包 | 版本/修订 | Content-Length字节 |
| --- | --- | ---: |
| Firefox win64 | 157.0 / 1555 | 129834277 |
| FFmpeg win64 | 1013 | 1663577 |
| Winldd win64 | 1007 | 128684 |
| CLI计划合计 | 三个包 | 131626538 |

Firefox直接URL为[官方Firefox1555 ZIP](https://cdn.playwright.dev/dbazure/download/playwright/builds/firefox/1555/firefox-win64.zip)，其余URL、最终重定向、ETag及Last-Modified完整保存在私有HEAD收据。总计约125.529MiB压缩传输，解压占用尚未测；HEAD长度与ETag不是下载内容SHA，也不是二进制许可证完整审查。Python requests对raw.githubusercontent.com的3次有界原始文件GET均DNS失败，错误保留；上述Mozilla源码由web工具独立实际读取，不声称本地已有其完整源码原件。

## 下一步受控执行合同

本轮已准备私有 `native-fixture.py`，默认运行只输出PREPARATION_ONLY，不启动浏览器。未来主执行者决定安装时，可将`PLAYWRIGHT_BROWSERS_PATH`指向全新私有cache，再由现有verification Python执行`-m playwright install firefox`，不安装到全局ProgramFiles、不启服务；下载后保存包长度/SHA、版本及包内许可。**本轮未执行这一步。**

随后的`native-fixture.py --execute`先在about:blank记录浏览器版本、原生CSS.supports函数、属性解析能力，要求引擎原生`CSS.supports('backdrop-filter','blur(1px)') === false`。若仍true立即失败，不伪造supports、不覆盖原生函数。仅在false后才读取冻结原CSS字节构造明确标记的无业务fixture，核对实际computed背景rgb(246,250,255)、截图及CSS前后hash，所有页面网络请求阻断；fixture不代表真实业务页面通过。脚本不会下载包、登录或访问业务。

只有该能力预检真实通过后，才由主执行者安排已有页面仅登录与打开面板的验收：不发消息/模型、不改DOM/CSS或前端源码/编译产物，保存原生能力、实际计算样式、截图、来源CSS与163指纹保护。实际业务页面当前仍 **NOT_RUN**，AI-AC01这格不能标通过。

私有目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/backdrop-native-capability-preparation/`。包含inventory、CLI dry-run、官方HEAD/失败GET收据、准备脚本。`native-fixture.py`默认实测输出PREPARATION_ONLY、0browser/network/SQL；没有可用无支持引擎，因此本轮没有执行原生false或fixture验收。
