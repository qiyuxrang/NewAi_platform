# AI-T12：已确认官网的联系字段深化，固定12家

时间：2026-10-18约05:00–05:10（北京时间）。本单元仅只读研究和候选准备，不代表已入库或全库资料完成。未修改企业、资质、队列、模型、前端、服务及共享执行状态。

本轮实际RO使用 `COALESCE(trim(field),'')` 核对：在库已有官网104家，其中电话空2家、邮箱空44家、地址空21家。按电话缺口优先、再邮箱/地址缺口及固定ID顺序选12家；NULL已纳入，未把只检查空字符串的结果当作准确统计。

先离线复核已有官网正文、原件及真实可见链接。仅对实际新链接发起5次连接：4次HTTP200取得完整正文、1次HTTPS证书过期失败；单公司最多2页，总预算18页，每次12秒、零重试。新读取成功覆盖3家公司，不把此前留存正文再次算新发现。所有成功正文排除head/title/script，保留完整raw/text、SHA、定位、公开IP、固定IP直连和实际TLS信息。未搜索、调用模型或登录。

形成2个互斥候选批次，共8家公司11个原空字段（邮箱5、地址6、电话0）。已实际运行 `validate_batch`，两个批次均PASS；验证进程SQL/socket/DNS均禁止，实际被调用次数0。格式通过不能代替维护审核或证实工商、资质状态。

| 批次 | 企业/字段 | SHA256 |
| --- | --- | --- |
| 复用原官网正文 | 6家9字段 | `7991eae9c6707c330eaa9c8c78e9fa438111501b7b0abe3437b7761c1d6e051a` |
| 新可见联系页面 | 2家2地址 | `b45d099dff1082cc83b6089bcb6b3bf15e68e69ea6056028d1641f5c5d21daea` |

来源与边界：

- [迅腾官网](http://centn.com/)、[归毂公司简介](http://www.guigug.com/h-col-251.html)、[数邦官网](http://www.shubangelec.com/)、[顺旺公司概况](http://www.shunwangjs.com/col.jsp?id=101)、[能控安远官网](http://www.nkaytech.com/)、[睿联官网正文](http://ruilianxinxikeji.com/list-hexinchanpin.html)复用本轮之前保留的实际正文和原读取时间，候选原件/hash逐项核对。只取明确企业联系信息；多办事处地址、明显旧址、招聘手机和用途专用邮箱保留缺口。邮箱按原字面保存，不因域名拼写不同而自行纠正。
- [胖柴服务城市](https://www.pangchai.com/cities)明确完整运营企业名、2026年8月办公点状态，候选仅取西安办公点；其他城市不混入主体地址。[中煤集团联系页](https://www.arscmh.com/node/230)仅取顶部“公司地址”，不借用所属公司、机构或招聘联系方式。
- 互智关于页仍无电话；榴莲既有正文未找到新的联系链接；淘丁可见联系链接跨到集团站点，未借用集团字段。睿联实际新商务合作HTTPS地址证书过期，停止且不降低TLS校验。未知均不解释为不存在。

私有恢复目录（含企业ID、版本、原空字段、原文及请求收据）：`.runtime/baichuan-ai-local/independent-enrichment-20261017/official-contact-gap-20261018-0500/`。

- 固定cohort SHA：`2cfb579a245a7d87e2d69ca7cdfd6890844b0c128dcdf526625699499ee5f70f`
- `journal-final.json` SHA：`48e12b93aad739422b287286a02703a3600bc7c53cbebbc9a7fb8875efed2cb8`
- `final-receipt.json` SHA：`3632c0d48b6e4e5b43b1e55a2b3595f5bdfa7032581c18742e983469964d224a`
- `file-manifest.json` SHA：`a6f4a42a4d78ad79635dc6023553a38bdd259f6e040544e872a1ca58f75925db`

可重复命令：私有目录中的 `prepare-offline-batch.py`、`prepare-new-body-batch.py` 仅RO读取；`validate-offline.py <批次文件名>` 使用company-test Python执行禁SQL/网络格式验证；`freeze-final.py` 离线核账并以独占新文件保存。所有输出使用独占创建，重放需新目录；不得为了复测重复请求已读取或失败URL。抓取脚本 `fetch-visible-contact.py <cohort索引> <实际可见URL>` 只接受已知同源或页面真实显式HTTPS链接，不跟随重定向。

尚待根维护者审阅原文及当前版本后决定应用；本报告不把候选数当已补字段数。电话两处缺口仍未知，资质和工商权威核实未增加。
