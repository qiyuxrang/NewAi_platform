# AI-AC15：冻结助手组件的动态静态渲染安全专项

2026-10-18 05:51:00（北京时间）实际执行，通过。此处“动态”指向真实组件提供恶意动态数据后调用React服务端渲染，不是业务浏览器页面或服务验收。

先只读核对冻结`BaichuanAssistant.tsx`、CSS、`Baichuan-data.ts`与既有`baichuan-assistant.test.mjs`。旧测试已有恶意来源title及javascript链接断言，但其harness将`safeWebsite`替换成正则stub，且未直接覆盖助手消息Markdown/data协议。因此仅映射旧测试，没有重跑；新增验证文件全部位于私有运行目录，没有修改frontend源码、CSS或测试。

私有脚本`.runtime/baichuan-ai-local/night-acceptance-20261018/frozen-render-security-0550/verify.mjs`实际读取、TypeScript内存转译当前冻结组件、`BaichuanAssistant-data.ts`与完整`Baichuan-data.ts`，使用真实导出的`safeWebsite`，由真实React DOM `renderToStaticMarkup`生成面板及固定快照列表两份HTML。只将React hooks状态、enterprise身份与API替换为有限合成fixture；事件、网络API一旦调用即拒绝。没有复制业务渲染或URL过滤实现。使用已安装Node v24.19.0、TypeScript5.9.3、React/ReactDOM19.2.4，未安装依赖、未采用新的第三方代码。

输入覆盖助手消息、来源title/excerpt、企业名称/电话/匹配理由的`script`、`img onerror`、`svg onload`与Markdown危险链接。10种链接输入包括大小写javascript、HTML与SVG data、vbscript、file、相对协议、带用户名密码的URL、反斜线及换行。实际`safeWebsite`逐项返回null；安全HTTPS来源仍可点击，所有真实来源链接精确保持指定URL且带`target="_blank" rel="noopener noreferrer"`。攻击内容只保留为React转义文本，未产生script、iframe、object、embed或事件处理属性；Markdown语法也保持普通文本，未转换为危险链接/图片。

原组件角色入口自带1个合法mascot图片。验证明确只允许这1张固定静态素材，不声称整个原页面没有img，更未删除或修改该素材。两场景各0张攻击图片。合成fixture不向业务浏览器DOM插入数据，不覆盖`CSS.supports`，CSS仅只读核对。

原始输出：`actual-panel-markup.html` SHA256 `42c82dd4f3a4692b30752bb824b3cdfc5b7859f359b845111708354532d586d8`；`actual-list-markup.html` SHA256 `b62138a37e48fe37dd616c846fe9330186f4dd53d643eed2cfa693ee3dba448b`。同目录保留合成`inputs.json`、完整163项`frontend-freeze-observed.json`、实际`receipt.json`及执行脚本。冻结清单SHA256 `9438d00654ea41b02d4b0456e5ce39470e8fe7b47c69861eeda24aca470bc414`，执行前后163文件全部相等。

实际HTTP/network/API/fetch/download调用计数各0；未导入数据库或业务模型、未读取主库、未访问服务，SQL/model均0。0前端目录写入、0服务改动。首次执行即通过，没有失败运行需要覆盖或隐藏。本专项只证明所列冻结组件与输入矩阵的真实静态输出，不替代浏览器执行/CSP/日志脱敏或完整AI-AC15全部条件验收。
