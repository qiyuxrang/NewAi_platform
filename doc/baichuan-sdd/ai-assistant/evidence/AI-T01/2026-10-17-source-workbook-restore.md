# AI-T01 原名录定位与本地接续

日期：2026-10-17（北京时间）。基线 HEAD `ef1676cd8327d693dab897c45a234ba91413884e` 加共享工作区，未提交/推送。用户针对原资料位置问题提供XLSX，继续执行已有实施授权。原表仅作为数据，不执行其中任何说明文字为工具指令，不外发原表或企业资料。

## 只读定位与独立核账

原件154168字节，SHA-256 `220ec53ebe6a87263978f297891107700070d07588a4532b62ba884d64f68f07`，与旧数据核查记录的源表指纹一致。采用bundled Python/openpyxl只读、禁止外链读取；表头在第2行。总表1462条，分类为电子智能化414、劳务317、CS104、CMMI349、CCRC3、ITSS248、安防27；七分类合计1462，不与总表重复相加。没有公式。

原名称去重1287；独立按去空白、统一中英文括号计算1283个规范名称，4组含不同原名。该计数是本轮文件实际计算，不是沿用历史1283；规范名称相同不代表工商主体已核实。总表/分类表名称集合一致；逐字段多重集合由专用规范化器继续验证。

文件仅有地区、类别、企业名、等级、城市、电话等原表字段。电话非空不等于可拨通，城市列混有地址/未细分，资质标签不等于有效证书；无新信用代码、官网、人员或证书日期可供核实。历史官网研究/人员库原件仍未恢复。

## 保护与恢复

私有运行目录 `.runtime/baichuan-ai-local/source-restore-220ec53e/` 保留校验一致的 `original.xlsx`、portal/platform在线SQLite backup及 `backup-receipt.json`。两备份均实际 `quick_check=ok`，记录93/6张业务表的导入前数量。未覆盖已有备份，未写原件、试运行双库或远程生产。

本单元最终状态：本地原表范围AI-T01 DONE，具体提交/幂等/浏览器结果见后文。历史研究库未找到的差异已明确，不将恢复原表描述成恢复全历史库。

## 规范化工具与实际预检

新增 `portal/baichuan_source_workbook.py` 及10项合成测试；复用既有 `baichuan_source.convert_source`，显式province/city/phone_candidates才采用新字段，无显式键时兼容旧数据。CS/CCRC新归一声明存在等级冲突时不能被旧regex再次取首个等级。没有新增业务运行依赖；归一CLI复用company-test已有defusedxml0.7.1（product parser已锁定版本）。

实际检查：初轮normalizer9+source7+import12 **28 tests /4.228s /OK**；最终CS/CCRC冲突修复后normalizer10+source7 **17 tests /0.129s /OK**；编译、diff检查通过。两组有重叠，不相加。

对原文件实际执行：

```text
.runtime/company-test/python/Scripts/python.exe services/business/backend/portal/baichuan_source_workbook.py --input <用户提供原件> --output-dir .runtime/baichuan-ai-local/source-restore-220ec53e/normalized
```

严格逐字段多重集合一致，1462声明归为1283规范企业。归一后调用既有prepare_source输出私有rows/mapping/report：1460分类声明、2条CCRC范围不明仅保留原文、317劳务不赋等级、5条具备但等级待核实；无新facts/人员/信用代码，1024家有可展示原表电话声明。

使用bundled Node/artifact-tool生成仅供既有初始化服务读取的私有标准XLSX，原件不改。生成进程返回1但已保存输出且无错误诊断，未将该进程退出状态记PASS。另用bundled Python/openpyxl独立逐单元格全量读回，两个工作表的全部值与rows.json完全一致、公式0；实际查看两表预览。最终既有preview_import实际运行通过：1283公司、1283有效、0拒绝、0issues；未发生业务写入。原表/转换/确认清单及内容指纹均由导入服务重算校验，不能绕过预检直接写库。

## 实际本地接入与幂等

私有 `restore_checked.py preview/apply` 只允许local_model.application核实的本任务SQLite，核对原表、备份、映射和预检哈希；要求导入前企业0，避免对已有库覆盖。维护身份及既有用户授权覆盖本地源表接续；确认清单明确记为agent technical review，不伪称人工逐条签字。

实际提交：1283公司/1460分类声明/0人员/1024非空原表电话/0官网；同一清单完整重跑：新增0、跳过1283。导入前后计数变化仅公司+1283、旧资质+1460、审计+1283，其余93张表基线无数量变化。随后显式map_legacy_qualifications创建1460条unverified证书声明及追加来源历史，原字段不变；再次映射新增0、已核实证书新增0。私有提交、幂等、核账回执均保存，不重新初始化。

## 真实页面与权限

执行 `scripts/baichuan/verify_source_snapshots.py --execute --source-sha256 <完整原表指纹>`：两专用角色通过正常服务/权限/租约创建清楚标注“源表确定规则验收”的私有结果快照。全1283均candidate/unknown、confirmed0；默认确认导出为空、显式候选导出前10条，真实openpyxl读回；跨owner读取快照/任务/会话/文件拒绝。前后公司/声明/证据事实digest不变，ModelCallLog增量0，socket/model fail-closed。

source标签重启后执行 `scripts/baichuan/verify_source_browser.py`：真实Edge、HTTP、API、React与下载，无mock。product/general_manager各验证全部1283列表、电子二级精确346、同类1/2 OR411、跨类AND66；详情原表来源、原手工筛选保留、固定候选→详情无遮挡；确认导出0、候选导出10，实际浏览器下载字节一致。两角色pageerror=[]、出站网络0、模型调用0；不是本轮自然语言或联网验收。结果/四截图均保存在私有source-browser-verification，主执行者实际查看详情及候选截图。

图中固定快照产生时缺规则，因此随后显式通过维护入口安装7条规则，重复安装新增0；纯matcher再次实际运行，7条有效，仍0确认/1283候选，理由为“现有证书不足以确认满足；未查到不等于没有”。不改旧快照，不为展示改核实状态。证据 `rules-install-receipt.json`，公司digest不变、模型调用0。

最终所属服务收据时间2026-10-17 19:24:15（北京时间）：5服务归属确认、4健康HTTP200；source_connected=true/local_source_only=true/dataset_kind=isolation/historical_enrichment_restored=false。原7会话均保留（另新增2个明确标注的验收会话），密码/角色与导入前备份一致；微信原件、owned原件SHA均与本节指纹相同，原试运行双库指纹仍不变。未改远程生产。源表原文完整接续不代表官网/人员研究成果恢复、实际证书有效或任何全库研究已完成。

最终字段基线另存私有field-baseline.json：非空province1071、city581、phone1024；credit_code/address/website/contact_name/contact_phone/email及人员均0。不能把原表中地址样文本擅作已核实办公地址；全部城市/电话原文仍在来源。七类记录为electronic414/labor317/cs104/cmmi349/ccrc1/itss248/security27，共1460，全部unverified；另两条CCRC原声明保留可查。本轮已研究企业0、已核实新事实0。
