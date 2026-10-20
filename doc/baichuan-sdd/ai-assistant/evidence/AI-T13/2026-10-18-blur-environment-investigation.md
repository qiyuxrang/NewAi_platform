# AI-T13：无背景模糊环境的验收缺口

时间：2026-10-18。仅研究公开浏览器实现与读取既有本机测试结果；没有修改前端、样式、浏览器DOM或服务。

既有Edge实际测试传入 `--disable-blink-features=CSSBackdropFilter`，但页面的CSS支持检测仍为true、计算样式仍有blur，故不能将其算作“不支持背景模糊”的真实环境。原结果保持NOT_RUN，不通过伪造 `CSS.supports` 或删改页面CSS使其变成PASS。

为排查原因读取以下一手来源：

| 来源 | 版本与实际观察 | 采用与验证 |
| --- | --- | --- |
| [Chromium历史功能开关变更](https://chromium.googlesource.com/chromium/src/+/5ff2d1bef3dd93aaf97ee01aff46719d3bb7114a%5E%21/) | 固定提交5ff2d1bef3dd93aaf97ee01aff46719d3bb7114a曾将CSSBackdropFilter由experimental改为stable | 解释旧开关名来源；未采用其代码 |
| [Chromium运行时功能列表](https://raw.githubusercontent.com/chromium/chromium/main/third_party/blink/renderer/platform/runtime_enabled_features.json5) | 2026-10-18读取main，无CSSBackdropFilter匹配；并非本机Edge对应版本 | 不能据此断言本机内部实现；实际本机检测仍为支持 |
| [Chromium CSS属性定义](https://raw.githubusercontent.com/chromium/chromium/main/third_party/blink/renderer/core/css/css_properties.json5) | 同次main读取，backdrop-filter属性段未声明该runtime feature | 提供进一步调查线索，不据此编造可用的新禁用参数 |

只使用来源说明开展诊断，未复制或引入第三方代码、依赖、二进制；无许可证采用事项，未对这些文件单独进行许可证审计。当前main没有固定到本机版本，明确限制其推论范围。

恢复点：无背景模糊环境兼容子项仍NOT_RUN；已有两角色、多宽度、减少动画、焦点及原列表实际交互记录仍有效。后续若取得真实不支持该属性的测试浏览器再独立验收，不因本缺口改变用户冻结的前端。
