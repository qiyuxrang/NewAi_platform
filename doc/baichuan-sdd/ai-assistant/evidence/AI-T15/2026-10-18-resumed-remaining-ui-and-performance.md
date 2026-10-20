# AI-T15/16/17：恢复执行后的时序、性能与剩余界面证据

记录日期：2026-10-18，北京时间。此文汇编08:18—08:26的原始收据，另只读核对哈希，不重跑模型、浏览器、解析器或测试。AI-D27跳过资料补全、AI-D28信任用户确认的原资质库保持；不重新核验旧库发证信息，不修改163份前端文件、构建、重启或操作远程环境。

本阶段并非全部SDD验收通过：真实首结果显示未达到5秒初始目标；文字与文件冲突提示、OCR不可用提示存在实际失败，主代理正在修复，本文不宣称已经修好。先前433项回归属于修复前冻结版本，不能代替后续变更的回归与加载。

## 原组件与合成接口的真实浏览器时序

08:23:51—08:23:59，在原13180页面、原React组件及独立headless Edge中分别执行产品和总经理角色。助手接口全部由浏览器context精确拦截，创建会话、发送和结果均为合成传输，不转发任何真实助手POST。原输入区实际发送两轮不同条件，各保留原生UUID：A为广东电子二级，B改为广州ITSS二级并带电话。模型未参与理解这些合成条件。

将A结果GET挂起，待B结果实际渲染后才释放A。两角色均出现A结果请求的原生 `net::ERR_ABORTED`；虽然随后 `route.fulfill` 成功返回，不能据此宣称浏览器接收了A正文。未绕过AbortController。释放后面板仍为B、城市广州，固定快照列表仍为B的snapshot ID及条件版本2，未被A企业覆盖。

| 检查 | 产品 | 总经理 |
| --- | --- | --- |
| 原输入两次、不同native UUID | PASS | PASS |
| B显示后才释放A，A请求实际中止 | PASS | PASS |
| 面板及固定列表保持B、版本2 | PASS | PASS |
| 合成传输下提交中DOM反馈 | 11.3ms | 13.6ms |

反馈使用真实点击及requestAnimationFrame观察已有DOM；仅当元素实际属于 `.bca-content` 时按内容区域裁剪，composer按viewport判断。没有编辑或注入DOM、CSS。11.3/13.6ms仅说明本次合成传输下的提交反馈，不是实际模型首结果耗时，更不是其P95。

原始目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/synthetic-ui-race-20261018/`。脚本 `race.py` SHA256 `b7c5ab8a65b246609ca41cd099a115cda31544a08ce88bf918f58df71442ff5b`；事前intent、每角色提交UUID、timeline、requestfailed、固定列表截图及前后库存均保留。`frozen-summary.json`列出的14份原件哈希已逐一复核一致。

两次现有账号API登录只在内存使用token，未输出或保存token。实际session34→34、原session行保持、last_login无变化。15个明确保护的业务/模型表全行哈希前后相同，含企业、资质、人员、1622证书、证据、修订、研究、会话、消息、任务、快照、附件、导出、模型日志。取样已有Model36/快照35，本单元增量均0。163前端及64原回归输入前后保持；此表保护不被泛化为所有审计/读轮询表的零写承诺。

这是“真实原组件＋合成传输时序”的验收，不冒充真实模型并发、真实后台任务或原生断网恢复；后者有各自独立证据。

## 当前旧库信任路径的隔离性能

原始目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/trusted-performance-20261018-0820-attempt3/`。真实执行约08:19:12—08:19:47，外层36.361秒，360秒硬期限，返回0、0跳过。每种规模1个连接冷样本＋5个热样本，共12条主链路样本；冷仅指关闭Django连接，不声称清空OS或页缓存。P95使用有限热样本的nearest rank，5个样本的P95即其中最大值，不是总体性能保证。

环境为Windows11、8逻辑CPU、Python3.13.16、Django5.2.18、SQLite3.53.1、openpyxl3.1.5。全新临时SQLite含真实旧 `CompanyQualification` 及新增未核实证书混合样本，覆盖精确二级、其他等级、UNKNOWN、新公开未核实、过期、撤销冲突及ABSENT。确认ID全集、分类、固定快照、默认确认XLSX及授权打开/三表读回均实际断言；未使用真实目标库或网络。普通主链路复用持久条件checkpoint，不用真实模型。

| 规模 | 热样本 | 结构化匹配P95 | 首快照就绪P95（不含模型） | 默认导出worker P95 | 主链路总计P95 |
| --- | --- | --- | --- | --- | --- |
| 1000 | 5 | 340.218ms | 456.574ms | 231.021ms | 836.569ms |
| 5000 | 5 | 1214.975ms | 1350.997ms | 863.826ms | 2546.367ms |

千家结构化匹配达到≤2秒初始目标；本次五千也低于2秒。这里的“首快照”是服务端结果就绪，授权结果render为API序列化，不是浏览器绘制，不能据此声称真实首屏≤5秒。

还实际执行两个独立任务的双worker，匹配区间真实重叠，总壁钟2617.091ms且各一个快照；同一任务双worker仅一方claim，唯一快照/attempt1/fence1；独立OS进程持有SQLite `BEGIN IMMEDIATE` 601.873ms后释放，claim约674.594ms并最终完成。单独慢模型边界采用唯一确定stub延迟1.2秒、任务时间预算1秒，真实终态 `budget_exhausted`、预留调用1、0快照、0自动重试。此stub不是实际模型或公网慢网调用；不把历史“用户无额外用量上限”改成产品新硬上限。

前两次原始失败保留：`trusted-performance-20261018-0820/` 首次计数断言失败；`...-attempt2/` 安装关系规则时隔离actor无维护权限。第三次是在准备规则/权限夹具修正后执行，不删除旧失败，不将失败样本计入通过延时。三次收据绑定的report、execution.log、frozen-inputs哈希均已复核；各229输入（64原输入＋163前端＋脚本及settings）是当时冻结范围，不能据此宣称主代理后续修复仍未经变更。

## 两角色真实首结果显示：未达5秒

主代理原始目录：`.runtime/baichuan-ai-local/night-acceptance-20261018/trusted-browser-visible-timing/`。08:20:15—08:20:40，两个角色各一次原UI文字查询，真实模型日志34/35分别4883ms/2503ms；无自动重试。要求陕西省及电子精确二级，343确认/940候选，与当时原库对应筛选一致，不能与未限省的346确认直接混比。

| 角色 | 首结果DOM | 首结果自然viewport可见 | 5秒初始目标 |
| --- | --- | --- | --- |
| 产品 | 8227.600ms（8.2276秒） | 8227.600ms | 未达到 |
| 总经理 | 5142.000ms（5.142秒） | 5142.000ms | 未达到 |

两样本的DOM与自然可见时刻相同，非后续手动滚动才变可见。原receipt总体 `status=PASS` 只表示流程与保护断言完成；其中 `first_rendered_result_target_5s_met=false` 保留，不能把该总体状态改写为性能达标或从两次样本推总体P95。

两角色 `feedback_ms=null`。原observer把不属于 `.bca-content` 的composer按钮也按该区域裁剪，造成反馈测量缺失；这是验收instrumentation缺陷，不是“产品没有反馈”的实测FAIL。原null及原收据不覆盖。本轮合成race修正观察范围测得11.3/13.6ms，只作为另一个明确边界的反馈证据，不回填真实模型单元的null。当前真实首结果超5秒仍是有效观测，不能被observer问题抹掉。

## 两个实际失败：修复结果待主代理另证

1. 文字与文件冲突：08:23:20—08:23:34，GM原UI合成文件二级与文字一级冲突，唯一真实Model36。快照保留文件二级自身引用，`conditions.unresolved` 明确一级/二级冲突，0确认/1283候选；但持久助手消息只有分类数量，没有给用户显示该冲突与澄清问题。原 `text-file-conflict-native/receipt.json` 为FAIL，不能以条件树内部保守为由改成界面通过。后端回复修复、回归和新实际复验由主代理追加，旧失败不重写。
2. OCR关闭：原 `ocr-disabled-real-worker-20261018-0826/receipt.json` 为FAIL。一份真实旋转扫描PDF经真实parser，OCR环境0，附件failed、0locator、原文件SHA保持；独立临时worker到达确定模型stub1次，该stub按本次验收约束抛出异常，job `processing_failed`、0快照、无助手说明。真实模型/网络/目标库均0。原件明确区分parser行为、stub异常及缺失的可操作说明；不能冒称实际模型失败，也不把“任何低可靠文字均不得交AI理解”增加为普遍需求。当前修复中，不宣称已通过。

## 已有格式与恢复证据矩阵

下表是独立时点证据的映射，不等同于在D28版本重新跑所有角色×格式的完整组合。D28主要改变旧库判定；已有parser、主体、逐项引用及恢复证据无需为凑矩阵重复模型调用。

| 场景 | 产品角色 | 总经理角色 | 边界 |
| --- | --- | --- | --- |
| D28可信旧库文字、默认确认导出、刷新 | 实际346确认；指定企业追问1家；真实下载1行 | 实际346确认；真实下载10行 | [当前D28证据](2026-10-18-trusted-legacy-robot-retrieval.md)，不是所有格式本轮重跑 |
| D28单独DOCX | 实际346确认、原生刷新 | 本轮未重复该组合 | 原始GM新文件已有下行单独证据，不倒改成本轮执行 |
| 两页文字PDF、旋转扫描PDF | 实际页/扫描引用及保守匹配 | 两份原UI唯一提交、queued收起/后台完成/原生刷新 | [产品文件](../AI-T09/2026-10-18-real-pdf-table-ocr-worker.md)、[GM两文件](2026-10-18-gm-pdf-scan-native.md)；高分扫描不冒低分证据 |
| 表格DOCX逐行引用、主体/等级/优先 | 修复后新固定ID实际通过，原失败保留 | 实际readback各行自身引用有效，原验收器FAIL另留 | [来源合并](2026-10-18-source-guard-merged-acceptance.md)；旧GM表格context刷新NOT_RUN不能补称PASS |
| GM新DOCX裸制造商二级与明确及以上 | 不重复 | 实际默认exact、明确at-least、ITSS优先，完整原生刷新 | [GM新文件](2026-10-18-gm-file-default-range-native.md)；独立于旧表格 |
| 实际在途关闭、列表操作、完成后刷新 | 原生单元PASS | 新文字、DOCX、PDF/扫描单元PASS | 见[产品在途](../AI-T13/2026-10-18-inflight-close-recovery.md)、[GM文字](../AI-T13/2026-10-18-gm-text-default-native-refresh.md)；不将D28普通关闭冒称关闭瞬间在running |
| 同存活context真实断网刷新→联网刷新 | v3原生PASS，v1/v2原验收器FAIL保留 | 原生PASS | [GM断网及关联读回](../AI-T13/2026-10-18-gm-native-offline-and-public-certificate-readback.md)，非注入cid伪恢复 |
| 新旧响应乱序 | 本次合成传输PASS | 本次合成传输PASS | 原组件/native Edge，0真实模型并发；A请求实际中止 |

完整入口多宽度、键盘、减少动画已有[两角色矩阵](../AI-T17/2026-10-18-owned-local-delivery-matrix.md)，其中一些历史NOT_RUN已由后续独立单元补证，应按时间读，不再为已做主链路开新查询。

AI-AC01剩余原生“不支持背景模糊”仍BLOCKED：官方Firefox运行库在page创建前出现WinError14001/SideBySide依赖问题；Edge所谓禁用特性参数实际仍支持backdrop-filter，不能替代。见[官方安装阻塞](../AI-T08/2026-10-18-native-backdrop-official-install-blocked.md)。前端冻结允许只读浏览器检查，但不授权伪造CSS.supports、改DOM/CSS或将未打开页面记为通过；本轮未再次安装或重试。

## 原件哈希与恢复点

以下路径前缀均为 `.runtime/baichuan-ai-local/night-acceptance-20261018/`，SHA256为本文只读实际核对值。

| 原件 | SHA256 |
| --- | --- |
| `synthetic-ui-race-20261018/receipt.json` | `3c0c787f66f749f1ef57a993dea7a07c7172849bcc75fbe436462acb044b7665` |
| `synthetic-ui-race-20261018/frozen-summary.json` | `c5f1f5d6d93b7b146b6293edaed9da78f45f059397a6d3391975136d72b06950` |
| `trusted-performance-20261018-0820/receipt.json` | `83594e072d6f8089a77c954bc7638f69cc827ed7e3aa7ebd8c445804abb4b450` |
| `trusted-performance-20261018-0820-attempt2/receipt.json` | `4c95ebe3aaf8ace801af225370606b4d149e1fe248b54f9329397a5a86000e45` |
| `trusted-performance-20261018-0820-attempt3/receipt.json` | `4ab75d77e1c93487d8a20a325ccf8edbfd4fe6b49329e434b975c217d8f79a24` |
| `trusted-performance-20261018-0820-attempt3/report.json` | `67dc96aa6ab7171469c2ba80d4d2fa69ca2964106aeb9b1988a1b295cd6d4389` |
| `trusted-browser-visible-timing/receipt.json` | `ad6de329640906c98dad425606f3ba84e4ad6e925ec5fd6ac374e003317b1222` |
| `text-file-conflict-native/receipt.json` | `a078fc2371b140f2494cc432910a5bdeafa5d3fe3da6f727ab05f3424a31cee4` |
| `ocr-disabled-real-worker-20261018-0826/receipt.json` | `10f7925b97f100f8c134ef0cea04873665954fcfc79f471c7772ea37766936b3` |

下一步由主代理完成两个真实失败的最小后端修复、相关隔离回归、实际加载及必要新ID复验；性能未达标与原生浏览器阻塞继续如实记录。本文只新增证据文件，没有更改原收据、共享任务/检查点/验收状态、业务代码、服务、主库或前端；资料补全仍暂停，远程环境未操作。
