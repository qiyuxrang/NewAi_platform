# AI-D33：连续检索吞吐与同类精确等级OR

完成时间：2026-10-18T16:34:11.366463+08:00。当前AI-T16单元通过，完整SDD余项保持原状态；信息补全延期，163前端冻结。

## 起点、修改与授权边界

用户“继续”。先核对AGENTS、README、progress、checkpoint、D32实际证据及工作区。现有本地路由仅1条product_assistant，名称“本地百川条件理解”，属于baichuan-local-existing provider及product模块；原4/min由scripts/baichuan/local_model.py初始化，本地_reserve按actor+route计一分钟窗口，并非上游账户配额。所属本地实际目录/SQLite与5进程身份已检查，远程及试运行库不动。

在线备份及原ModelRoute.full_clean、事务/CAS后仅把该路由max_calls_per_minute由4改30，同时更新时间；全表摘要确认其他表全同，原路由其他字段未改。配置实时读取，无配置重载或服务重启。上游账户30/min配额未核实，不据本地值声称可用额度；只报告实际6调用窗口。保留模型网关并发1、worker串行、pending限制、120秒任务超时、有限失败/容量等待、防重复调用、权限与fence。query模型调用次数预算仍为null，不是30次总预算。若需恢复4/min，必须按当前route/model/updated_at做CAS，不得用备份覆盖后续企业或会话。

## 真实首批失败及修正

首批6条均成功经过上游，无本地容量等待，30.944秒；严格语义仅5/6，M02以invalid_model_conditions终止且无结果快照。网关日志success不等于业务成功；原FAIL及6次用量完整保留。模型原响应未持久化，不能推断具体JSON/条件字段错误，也没有事后改响应取得PASS。

为稳定常见明确OR并减少调用，新增独立baichuan_exact_or_grammar.py，原AND语法文件不改。仅在已有本地语法开关开启、首轮无附件/恢复/文件约束且整句完全识别时，将同类别两个精确等级编译为any；支持同类别重复别名及限定名称/电话/条数输出。未知类别/等级、否定、优先、其他主体、日期、及以上、跨类别或、混合逻辑、地区或任何余词不部分提取，仍走模型。含OR父轮追问继续模型，保留原any，不擅自展平。原编译器、逐项来源、等级、旧库信任、四值匹配和权限均不放宽；电话仅输出，空值企业仍保留。

没有新增依赖、第三方代码或外部资料引用；使用项目既有schema、别名及规则。

## 当前源码检查

新配置/原容量恢复16项PASS（实际测试7.376秒，含建库等命令14.411秒），0外部模型。新OR及原语法专项28项PASS/3.214秒；其中11新OR项已包含在本轮完整回归中，不累加为独立覆盖总数。完整44模块582项PASS/288.039秒/0skip，80输入在运行前后及加载时保持。包括两项实际OS子进程终止恢复，旧fence拒绝，原断言不改。

保留两份测试准备失败：私有配置runner首次发现16项但因TEST.MIRROR初始化缺失而0项执行；修正仅保留原TEST选项并改临时NAME。OR专项首次28项有3项fixture安装权限错误；修正仅在隔离规则安装时授权维护，真实测试查询身份仍只读。原日志保留，不把失败计PASS。

2026-10-18T16:28:34.642203+08:00再次在线备份后仅加载所属portal/worker，新源文件与完整回归map一致。前端PID21632及两个网关保持；0migration/seed/模型探测/前端构建或重启。

## 新当前版本真实连续批次

冻结输入/预期后按顺序执行7条，其中6模型需求及1本地OR，34.640秒内完成，7/7严格PASS，0本地等待/0自动重试/无重复模型调用。

| 用例 | 实际路径 | 确认 / 候选 | 提交到首结果API | 状态 |
| --- | --- | --- | --- | --- |
| M01 | model | 64 / 1219 | 3.520s | PASS |
| M02 | local | 411 / 872 | 1.020s | PASS |
| M03 | model | 346 / 937 | 4.639s | PASS |
| M04 | model | 0 / 1283 | 4.792s | PASS |
| M05 | model | 0 / 1283 | 3.126s | PASS |
| F01 | model | 346 / 937 | 5.618s | PASS |
| D32-generic | model | 0 / 1283 | 3.005s | PASS |

完整1283企业ID与动态SQL oracle一致，无漏重；硬/软、主体、日期、引用、字段/数量、未知及冲突均保持。M05指定未来投标日、普通未来日期均0确认/1283未知；文件每项仍绑定自身附件块。当前本地OR确认411、候选872，与完整SQL一致。模型6例中位4.080秒，样本P95/最大5.618秒（n=6）。文件5.618秒未达全请求5秒口径；普通文字本批最大4.792秒，但有限样本不保证总体P95，不削减原验收。

## 原页面实际验证

原产品工作台使用唯一M02原文，实际页面发送、完整411确认ID核账、真实reload后同cid/sid恢复PASS。0模型/0token，提交反馈9.600ms，首结果自然可见1.9966秒，无显式滚动；只有1样本，不是总体P95。真实截图已查看。只注入既有平台登录token，BusinessLink原表单正常登录一次；未注入cid/UI状态，未改DOM/CSS或前端文件。新增正常认证session1，旧session及用户其他字段保持。

## 用量、保护与交付边界

首批6+新批6=本单元实际12模型，输入16711 / 输出1808 tokens；首批失败的模型消耗也计入。原页面0模型，隔离测试无真实模型。模型次数不设预算上限，有限验收样本不构成人为调用总预算。

原企业/1460旧资质/1622证书、资料、非空值、研究、历史任务/快照/日志/旧session全部保护；原Excel和试运行库hash保持，前端163文件不改/回退/构建/重启。企业事实写入0，研究/搜索0，远程操作0，无提交推送。当前只读核账：{"companies": 1283, "models": 67, "snapshots": 81, "conversations": 83, "jobs": 110, "sessions": 39}，4健康200、5所属进程且无在途任务。

本单元不宣称任意模型结构错误均已根除，也不宣称所有查询5秒达标；未覆盖的表达仍受严格编译器拒绝。AI-T13/15/16/17余下性能/角色/兼容组合按原边界记录，全库资料继续延期，自动化保持PAUSED。

收尾只读核账首次因D30/D31观察器各自计算的历史演示SQL expected_confirmed_ids不同而停止，诊断保留在closure-observer-binding-diagnostic.json。修正仅将当前收尾绑定原UI使用的D31观察器；API/UI之间强制仅该派生oracle字段可不同，所有真实行、摘要、计数和任务字段必须完全相同。未放宽数据保护、企业结果SQL或业务验收。

## 证据及恢复点

| 证据 | 私有路径 | SHA256 |
| --- | --- | --- |
| regression | `.runtime/baichuan-ai-local/night-acceptance-20261018/d33-continuous-throughput/regression/receipt.json` | `57f2a2e0135b3e4efe75a8c05a413934cffd2dc61bfaf94d7e04201c04de61ea` |
| backend_load | `.runtime/baichuan-ai-local/night-acceptance-20261018/d33-continuous-throughput/load/receipt.json` | `42267fa12fc38c53b4d9eee4dc7832911fbdac7a2253b82b306e74f668e1a0e1` |
| configuration | `.runtime/baichuan-ai-local/night-acceptance-20261018/d33-continuous-throughput/configuration/receipt.json` | `48c66b277ab9d54bf2a762a059dd858ae9bc752a48e36a75b8cb40e9be720ce3` |
| first_real_5_of_6 | `.runtime/baichuan-ai-local/night-acceptance-20261018/d33-continuous-throughput/api/api-receipt.json` | `8c58925760fc3ec0c9a29759ff5796aec80a90f812637e8e2a4d7c143b6c964e` |
| final_real_7_of_7 | `.runtime/baichuan-ai-local/night-acceptance-20261018/d33-continuous-throughput/api-final/api-receipt.json` | `81554100133bd224aa89d8c8e9e7171847be6e0ce578a27640d20b5071f5c013` |
| native_exact_or | `.runtime/baichuan-ai-local/night-acceptance-20261018/d33-continuous-throughput/browser/receipt.json` | `ef8221488061faee5fff0ded675c8ca24588d4e60bd4edf3cee0982ccf406540` |
| isolated16 | `.runtime/baichuan-ai-local/night-acceptance-20261018/d33-continuous-throughput/isolated-final/receipt.json` | `62922244a8dd8d4f92e73027102f084b364641e80aa100ab097f642397c48c77` |
| closure | `.runtime/baichuan-ai-local/night-acceptance-20261018/d33-continuous-throughput/closure.json` | `2d3d7ed81bd814764ae803abb766cd60edee16358a78d6cebf3a7b90aacd6875` |

后续从本单元closure及checkpoint恢复，不重复本轮批次、已修M05或企业研究；继续剩余性能与角色/兼容验收。保护原模型配置与技术限制，前端冻结不解除。
