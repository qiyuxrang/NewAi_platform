# AI-D42：本机集成环境两种助手检查

2026-10-19，承接用户“启动项目代码”“不是还有AI助手检验吗”及“两者都检查”。当前目标为3080前端、8080代理、8100业务和18411模型网关，数据库为`services/business/.runtime/portal.sqlite3`。此记录不使用13180历史环境的通过数字代替本轮验收，不涉及远程部署或GitHub发布。

本轮接入与下述已执行功能检查完成；未执行的完整矩阵仍按原状态保留。

## 实际修复与接入

- 标准启动遗漏百川Worker，现已复用现有启停、只读预检及PID/创建时间/命令归属检查纳入；助手关闭时仍只启动原三个Worker，开启时启动第四个。tender未加入默认启动。
- 现用库在线备份后，使用现有总经理维护身份调用既有`install_compatibility_rules`，仅增加七类系统规则及七条规则依据。按既定可信旧库策略启用查询、本地语法及同一`default` scope；没有重新导入企业、生成证书或补齐企业事实。研究和事实写入保持关闭，角色权限没有修改。
- 业务解释器安装仓库锁定的`defusedxml==0.7.1`、`openpyxl==3.1.5`、`et_xmlfile==2.0.0`。DOCX入口直接使用defusedxml，已同步业务依赖声明；Excel沿用原可选依赖文件。
- 产品智能助手发送前网络失败后，“重新加载历史”原会清空未发送草稿，首次会话恢复持续失败还会丢失恢复按钮。修复仅在显式错误恢复保留草稿，并显示中文网络提示；正常新建、切换及权限失效仍保留原清理规则，共享API未改。
- 百川“电子与智能化一级或二级，前3家，加上电话”原不能完整消化两个输出片段，模型一次返回非法条件，显式重试又误提为AND。已在共享输出解析器接受完整识别的一段数量加一段加字段，复用原解析并保留顺序、范围及未知尾文拒绝；OR维持`any`，不放宽资格条件或吞掉未识别内容。原失败任务与错误快照保留。

## 实际功能证据

| 检查 | 本轮结果 |
| --- | --- |
| 产品智能助手真实模型 | 原页面17+25回答42，模型调用日志1836成功，输入1894/输出11 token；刷新重开保留答案 |
| 产品智能助手授权知识检索 | 原页面实际调用knowledge_search，返回3个授权来源；回答±0.5cm与提问前读取的原文一致，K2引文同时匹配检索片段和原文。点击K2查看全文返回200，打开内容与提问前全文一致 |
| 产品智能助手异常恢复 | 首问/既有历史两种页面，发送前浏览器局部断网、持续失败、网络恢复均保留未发送草稿；0额外模型调用 |
| 百川产品文字与追问 | 精确二级完整确认346家，与当前SQL全部ID相同；前3家追问前2家及官网，结果条数遵守请求 |
| 百川总经理DOCX | 真实合成资格附件经原页面上传、解析、模型理解与Worker完成，精确二级确认346家，显示前3家；并非创建虚构公司 |
| 百川产品文本PDF | 原页面上传实际文本PDF，ITSS精确二级确认集合与当前SQL全部ID相同，显示前3家；本轮没有扫描OCR实测 |
| 百川修复后原OR句 | 真实页面再次使用原句，完整确认411家，与SQL全部ID相同，显示3家；刷新恢复通过，0新增模型调用 |
| 百川跨资质AND | 电子与智能化精确二级且ITSS精确二级，完整确认0家，与当前SQL交集相同；没有把候选升级为确认 |
| 下载与读回 | 产品/总经理原页面完成Excel任务并下载；接口原始字节重新读回，名称、电话、顺序与固定快照一致，分别2行/3行；零确认导出0企业行。三份原始HTTP内容SHA256与服务端文件哈希相同，无VBA内容 |
| 会话与归属 | 产品/总经理均验证收起、重开和原生刷新；他人conversation返回404。修复后产品会话的他人job及snapshot也返回404 |
| 前端错误 | 上述百川真实浏览器没有pageerror；产品页受控网络错误已修复并复验 |

原页面下载后本机路径出现了`.xlsm`文件，因此未用这些变动后的本机文件冒充服务器原始下载内容。读回另从同一已完成导出的原下载接口获取字节，以中性后缀归档，逐份验证服务端SHA、OOXML内容和快照数据；未执行任何宏，也未把本机后处理归因于应用源码。

模型网关日志1836—1843共记录产品知识助手1次、百川条件提取7次成功传输；其中原OR语义错误和非法结构不能因网关成功而记为功能通过。修复后原句及AND实际均由封闭解析执行，新增模型调用0。

产品知识检索补验另有日志1849、1850两次成功调用，共输入5170/输出145 token；该问题没有调用联网检索，点击来源未新增模型调用。单次浏览器观察5.993秒，不作为整体性能指标。两段日志之间存在其他业务调用，不归入本轮助手用量。

## 实际检查

- 六个后端模块发现76项，75通过、1跳过，无失败/错误。模块为assistant、api_permissions、unreadable_attachment、exports、research_security、product_intake。测试库仅内存，真实网络/模型调用0；24个解析子进程使用当前部署解析器。唯一跳过项引用缺失的旧cloud-ocr路径，保留跳过，不能算通过。
- 输出解析修复三个后端模块44/44通过、0跳过，覆盖原句OR、完整AND、反序输出、日期/文件/优先项继承、未知后缀、数量冲突及非法范围；先红证据保留。仅内存测试库，真实网络/模型0。
- 前端产品及部门助手3项通过，TypeScript、单文件ESLint与生产构建通过；构建仅有既有大chunk提示。已在3080实际页面复验修复后构建。
- 现有`check-bundled-start.ps1`通过：启停脚本语法、启用/关闭选择、scope、严格进程归属、只读预检、CLI派发与路径检查；主代理再次执行通过。实际四个Worker均有唯一所属进程，externalCount均为0。
- 最终数据库quick_check通过、foreign_key_check为空。企业1283、旧资质1460、人员125的内容摘要保持；证书、企业事实修订、研究manifest和研究item均为0。本轮新增的七条依据属于系统规则。
- 72张既有业务表中65张全表摘要一致；五张文档表因并行业务新增任务/版本/来源/尝试/步骤，产品知识会话表新增1条本轮检索验收会话，所有原行逐字段保持；原审计行全部保留，新增审计为正常操作记录。没有停止或回滚其他业务来制造静态通过。

## 改动文件与恢复点

应用：`frontend/src/business/product/ProductKnowledge.tsx`及既有前端测试；`services/business/backend/portal/baichuan_output_intent.py`及既有输出条件测试；`services/business/requirements-main-acceptance-venv.txt`、`services/business/pyproject.toml`。

启动：`scripts/run-business-service.py`、`start-business-workers.ps1`、`stop-business-workers.ps1`、`start-enterprise.ps1`、`stop-enterprise.ps1`及既有`check-bundled-paths.py`、`check-bundled-start.ps1`。启动说明和本SDD对应规格、方案、任务、验收、进度、检查点同步更新。

本机私有证据根为`.runtime/enterprise/assistant-check-20261019/`：`product-assistant/repair-report.md`、`backend-regression/receipt.json`、`backend-regression/output-intent-fix/fix-receipt.json`、`worker-integration/result.json`、`baichuan-browser-result.json`、`final-ui-result.json`、`xlsx-readback.json`、`protection-result.json`及实际截图。包含`verify-baichuan.py`、`verify-final-ui.py`、`verify-export-readback.py`等可重跑脚本；旧准备错误和原失败不抹除。`verify-supplement.py`保留修复前OR失败现场，不能作为最新全组PASS入口。

授权知识检索补验：`product-assistant/rag-check/validation.json`、同目录`report.md`和`07-exact-K2-original-fact.png`，记录实际工具完成、两次模型调用、精确来源打开及回答与原文比对。

现用库备份`portal-before-assistant.sqlite3`与原私有配置备份仅留本机，不公开、不覆盖源库。既有13180历史交付检查点保留；当前集成环境单独写入`checkpoint.json.local_integration_check`。

## 本轮未执行

扫描OCR、全浏览器/设备矩阵、全知识库检索准确率与覆盖率、联网检索质量、全部复杂语言正确率、性能全指标、正式文件生成与正式部署未作本轮验收。单个授权知识检索及全文引用场景已通过，不等于全库质量验收。企业资料补全继续延期；本次查询功能通过不代表企业所有字段已有可靠资料。未提交或推送本轮改动到GitHub。
