# AI-T12 H1：已有HTTP/HTTPS失败官网线索的独立复核

2026-10-18执行。本单元仅发现及复核候选，**未写业务库**、未调用业务模型、未重复搜索、未修改前端或服务。候选交根执行者审核，实际补入数仍为0；不得把下述16个候选计入已补字段。

## 固定范围

只读扫描此前`research-*`、`deepening-*`资料记录，按实际库当前ID/名称/版本及空官网筛选，排除所有已保存`cohort-night-*`名单和已填官网企业。固定20家，先保存`cohort-http-h1.json`并告知`local_start`；该代理确认W12已排除全部20家，避免重复。包含此前亿创实际HTTP正文及其HTTPS失败收据，其他域名均来自已有记录，未凭记忆补造域名。

私有目录：`.runtime/baichuan-ai-local/independent-enrichment-20261017/`。源库连接使用`mode=ro`、`query_only=ON`。本批未重试任何已有失败HTTPS链接，未放宽TLS校验，未回写旧journal。

## 实际获取与保留边界

- 20家完成本轮HTTP路径核读尝试；其中2家DNS失败。初次读取及6个人工检查后的同源补读，连同1份Edge成功正文，共保存25份HTML/渲染DOM响应；非200响应9份如实保留，不作为字段依据。
- 普通读取禁自动跳转，HTTP→HTTPS及跨域重定向均不跟随。相对HTTP同源落地页在人工核对后单独指定。已知host先检查DNS结果均为全局地址；这是本次人工有界访问，**不把离线URL校验或该DNS检查冒充未来通用抓取器的DNS固定/SSRF保证**。
- 亿创及华跃的JavaScript页面另用现有verification Python和本机Edge，正常TLS设置、拒绝下载/service worker；仅当前指定HTTP origin的GET、文档/脚本/样式/XHR/fetch，最多40次允许请求/页，阻止其他origin、协议及资源类型。实际允许HTTP GET 20次、拦截34项；亿创取得实际版权正文，华跃未获合格正文，未生成候选。
- 5份响应实际为gzip。保留原始wire字节和原hash后，离线有界解压重新提取；未额外请求。初次错误解码文本保留并标明，不作为候选。最终纯文本仅取HTML body、排除head/title及script/style/noscript/svg/template；不以标题含全名代替正文含全名。
- 当前有10家可审阅官网候选，另10家保存访问限制/正文或主体缺口。亿创仅提原HTTP官网，旧版权2009–2016中的地址留作历史线索；华跃仅标题有全名、正文为空，明确拒绝。其他页脚/运营方、招聘及多办公室联系方式未硬填；证书陈述只留原文，不写证书或等级。

## 冻结候选与检查

`batch-http-h1.json`包含10家16个当前仍空字段：官网10、电话2、邮箱2、地址2。所有来源显式`publication_kind=corporate`，原HTTP scheme/host及默认端口一致；保存实际正文、准确全文定位、获取时间及SHA-256。官网以外字段均为原文字面值；云联地址保留原文换行。该批只表示已复核企业公开披露，不授予工商身份或发证机构authority。

根执行者可按既有显式SHA维护工具审查后执行，本代理没有执行该命令。当前D24 `validate_batch`及Django逐字段`clean`实际通过，验证子进程关闭网络且没有打开任何Django数据库连接。全部候选ID/版本和字段空值已从真实所属库重新只读核对；之后若版本变化，仍须由维护工具CAS拒绝，不可绕过。

| 私有文件 | SHA-256 |
| --- | --- |
| `cohort-http-h1.json` | `c7b3c81b4d0f4c1e3436c8e83976f8689d9fb375eb9fcb21b18b3c216bef0f4f` |
| `research-http-h1.json` | `e4c8d8d1564017ab5bb78bef793417bd4e0380ff9111c81cbe310cc307dbf32f` |
| `batch-http-h1.json` | `9c7f7c047e20d72a8752d3927b3225981792affaefe4746e345968dc71bcaa43` |
| `http-h1-validation/receipt.json` | `8015f318bcb7a46e3984883598eb8ac49001402438695d1a8638e7510d00681d` |

原文件/文本和各hash位于`http-h1-raw/`；最终计数见`h1-review-summary.json`。复核工具为同目录`read_http_h1.py`、`read_http_h1_contacts.py`、`read_http_h1_edge.py`、`build_http_h1.py`，均只为本次固定名单；原始抓取文件使用独占创建，不能重跑覆盖。起初公司测试环境缺bs4，在任何网络获取前失败；改用标准库HTMLParser，没有安装新依赖。华跃Edge断言失败的原收据保留，未包装为正文成功。

下一步由根执行者审核这10家/16字段、既有备份/CAS维护工具落库并实际重放核对。本轮20家是已发现线索的深入复核，不增加全库首次发现企业分母，也不代表完整字段研究或证书核实完成。
