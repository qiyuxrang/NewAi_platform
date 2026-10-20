# AI-D34：角色验收、流式接收及本地运维交付

状态：PASS_SCOPED_D34_ROLE_STREAM_AND_LOCAL_HANDOFF。仅本次选定范围完成，完整性能/全浏览器/全库补全不标PASS。

## 用户范围与实现

用户明确选择角色/文件/追问/登录/导出组合、浏览器兼容与本地收尾，新增流式回答；进一步允许只改助手接收逻辑，外观不变。原163项冻结清单保留，例外仅`BaichuanAssistant.tsx`及其既有测试文件，其余161项、CSS、JSX布局/样式/入口、前端进程仍保护。原JSX仅消息数组绑定改变，以同一消息元素显示增量内容，不增加控件。无前端构建或重启。

新增`POST assistant/jobs/{id}/stream/`仅接收空对象，观察已有query任务，不创建/领取/取消/重试任务，不消耗模型、不写企业事实、不研究。复用已有apiEventStream、业务会话认证及网关SSE转发。25秒观察窗、250ms检查、至多6次客户端观察窗；失败回退原1.5秒轮询。每帧检查实时权限、session_version、真实会话存在/到期/身份/认证hash和当前条件版本。只发送固定真实阶段和worker已发布的公开答复；不展示原始模型JSON/附件正文/checkpoint或思维链，不使用延时打字。断流不终止后台任务；重连读取当前提交状态，不重放模型请求。该实现是任务进展与校验后答复的增量传输，不宣称模型token级生成或全场景5秒。

旧库来源实际缺口：可信旧资质匹配原本固定evidence_ids为空，导致真实XLSX缺少已有源表定位。修复仅为新结果沿既有旧资质→映射证书→mapped_source修订→同企业/同scope的legacy_import来源链附带引用；逐项核对当前原声明/类别/等级/证号/日期/来源hash/主体等，错链不引用。资料仍按用户确认可信，来源/证书原unverified身份不升级，旧快照及资料不改。

## 依赖研究

运行依赖Django 5.2.18（既有依赖、BSD-3-Clause），查阅[Django 5.2 StreamingHttpResponse](https://docs.djangoproject.com/en/5.2/ref/request-response/#django.http.StreamingHttpResponse)和[MDN ReadableStream](https://developer.mozilla.org/en-US/docs/Web/API/Streams_API/Using_readable_streams)，2026-10-18访问。采用有界同步流观察，顺序消费/取消；复用项目自己的读取器，不复制第三方实现、不新增依赖。MDN说明文档按其CC-BY-SA授权提供，本项目未复制其示例代码。WSGI每条连接会占用线程，25秒有界和原轮询保底不等同于高并发容量已通过。

## 实测记录与失败保留

- 流式首轮11项实际PASS，7.340秒；独立审查补充真实session撤销。扩展14项首次13通过、1测试准备ERROR：用户外键受保护，测试直接删除用户失败；改为测试无法解析的旧身份，未移除实际logout/expiry覆盖。首轮工具输出保留于聊天工具记录，最终统一回归另留文件日志，不能冒称首轮14项全通过。
- 前端12项实际PASS，包含逐段接收/收起继续/持久答复替换/旧轮次丢弃/断流不重发；TypeScript和针对助手ESLint实际通过。初次ESLint从错误工作目录启动未找到配置，改回frontend工作目录后通过，没有改配置。私有`d34-streaming/frontend-checks/receipt.json`及三个日志绑定实际新执行。
- 新旧库来源链/可信策略/补链/导出四模块52项PASS/27.337s/0skip，包含实际XLSX读回和旧快照保护；52与最终统一回归重叠，不相加。收据`.runtime/baichuan-ai-local/d34-legacy-export-sources-receipt.json`。
- 原页面角色批次首批追问实际结构单叶与all单叶合法等价，但脚本按树字节比较FAIL；独立只读复核完整谓词/来源相同。独立第二批发现真实导出来源缺口，FAIL保留。两批共8模型、13358prompt/1504completion。保护脚本将新导出整表误判为保护变化，已只读核对原行全保留，不改原FAIL。证据`d34-role-matrix-final/independent-readonly-audit.json`。
- 两角色0模型原生刷新最终有限批PASS：完整平台/业务表单、实际新会话、陕西精确电子二级动态SQL343确认、原生reload同CID/SID；Edge1440及1024宽面板在视口内。前次准备冻结例外未登记及346省份oracle错误各保留，未改业务结果。证据`d34-native-refresh-sql/receipt.json`。Chrome不在标准安装路径；原Firefoxloader阻塞未改系统重跑，不能宣称全浏览器兼容。
- 在线备份→恢复副本演练PASS：93表schema/全行逻辑摘要一致，quick_check和integrity_check正常、FK异常0；主库保护表前后相同、0模型/0主库覆盖/0重启。绑定16:53历史时点，不假称最终源码已加载。见[本地运维说明](../../local-operations.md)及`d34-local-operations/receipt.json`。

私有证据根目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/`。全库补全延期，新增公开观察不继承旧库信任；远程生产/试运行未操作，自动化仍PAUSED。

## 最终执行与版本绑定（2026-10-18T17:21:05.165268+08:00）

- 当前46模块603项实际PASS，293.868秒，0skip，85源码/测试输入保持。首次统一603为1 FAIL（旧权限路由清单仍为13项），保留原收据；将新增流入口纳入全部权限矩阵后，目标21项及最终新603通过。期间测试关闭response触发Django request_finished关闭外层测试事务的问题，仅改为关闭观察生成器，保留所有权限断言。52来源测试/21权限流测试均属603子集，不相加。
- 前端12项行为、TypeScript noEmit、助手ESLint实际PASS；原163项清单SHA保持，2项授权例外，其余161不变；将唯一messages数组绑定归一后，整个JSX尾部与旧文件相同。0构建/0前端重启，原PID21632保持。
- 17:18:05所属portal/worker已在在线备份后加载当前源码；5所属服务/4个健康HTTP200。无迁移、seed、模型健康调用或企业资料写入。4个受保护资料维度和原Excel/试运行库摘要保持。
- 两角色均通过完整平台及业务原表单、DOCX、追问、运行中收起、原生刷新恢复和默认确认Excel实际下载；4轮全量1283企业ID与动态SQL一致：346确认/937候选/0排除。两份XLSX各10企业、3工作表、无公式，企业名/电话一致；每份10条均有原证据ID、来源标题、实际源表行和证书ID。原unverified不升级，旧资料/旧快照不变。
- 各角色1次真实SSE，在完成前有17个非空传输分块（包含心跳，不能说17段答复），各3次真实可见阶段变化。首可见分别比完成提前3687.163/3690.464ms；这是提前量，不是查询首结果响应时间。最终摘要来自worker持久消息，非模型token流、非切割完整答案延时播放。
- 最终角色批4次真实模型，6637prompt/736completion；此前两失败批8次、13358/1504完整保留，D34总12次、19995/2240。无人工调用预算上限，保留计量及技术保护，无重复提交/研究。
- 在线备份→恢复副本93表schema及全部行摘要一致，quick_check/integrity_check正常，FK异常0；演练绑定16:53时点。只读最终闭环通过，当前1283企业/79模型日志/97快照/93会话/130任务，无在途任务；不是平台库/文件/密钥协调灾备切换，也没有覆盖主库。

| 绑定项 | 私有文件 | SHA256 |
| --- | --- | --- |
| regression | `.runtime/baichuan-ai-local/night-acceptance-20261018/d34-streaming/regression-final/receipt.json` | `148a156ef5b4826404fc8f633e1e9dc722f13d05522c7ff108ebd8eea91f7575` |
| load | `.runtime/baichuan-ai-local/night-acceptance-20261018/d34-streaming/load/receipt.json` | `2c65f53f65ddc5cae08ae2acba4c3bfffcdac44b19e68626b3140935132d99f7` |
| frontend_checks | `.runtime/baichuan-ai-local/night-acceptance-20261018/d34-streaming/frontend-checks/receipt.json` | `7a5c3448a1fdf088b30b9c947fb3753b0cdf506f866d5dcc74a8d9d586fcb157` |
| role_stream_matrix | `.runtime/baichuan-ai-local/night-acceptance-20261018/d34-stream-role-matrix/receipt.json` | `5a89a17e55e340bfeee0e2db3a9df0ddc901210bac3cbe85adf8521e4689715c` |
| native_text_refresh | `.runtime/baichuan-ai-local/night-acceptance-20261018/d34-native-refresh-sql/receipt.json` | `dcae717d69df1d92f391aa178fd4f4034c3dcaaa742d16fbeb6dd9d273aaad5a` |
| backup_rehearsal | `.runtime/baichuan-ai-local/night-acceptance-20261018/d34-local-operations/receipt.json` | `58450ebf937a663460801fffa2787d14c79d42b58065a4da5e70af276103b35e` |
| first_regression_fail | `.runtime/baichuan-ai-local/night-acceptance-20261018/d34-streaming/regression/receipt.json` | `b5c977569805c546a1876a47c950dfb7210dae4cb2fe627233e28e595eb1d30a` |
| 最终只读闭环 | `.runtime/baichuan-ai-local/night-acceptance-20261018/d34-streaming/closure.json` | `dc8baea041ef9b7875a614c7e790e271d20e9cbad20ae9324c6986ced3dfc787` |

当前结论：选定角色组合、阶段与结果流式接收、本地运维交付PASS。Edge已测双视口；Firefox本机loader阻塞，Chrome标准安装缺失，不能写全兼容。全查询5秒目标和完整性能矩阵未通过；全库研究/字段核实本单元新增0，继续延期；远程未操作，自动化保持PAUSED。接续不得重跑已完成12次模型或成功角色批次，按checkpoint仅推进剩余明确场景。
