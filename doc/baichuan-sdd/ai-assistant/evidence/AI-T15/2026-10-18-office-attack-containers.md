# AI-T09/15：真实Office解析CLI安全容器检查

时间：2026-10-18T03:16:22.086804+08:00。仅公开合成内容，不接触企业库、模型或页面。实际使用现有cloud-ocr Python、`-I -B`及当前source_parsers/cli.py逐个启动8个独立解析进程；固定输入/输出/源码SHA均保存。不是mock safe_zip，也不是只看防护代码。

| 固定用例 | 输入字节 | 实际结构化结果 | 秒 | 结论 |
| --- | --- | --- | --- | --- |
| valid-control | 458 | completed | 0.1527 | PASS |
| high-compression-2mib | 2616 | archive_limit | 0.1449 | PASS |
| internal-dtd-entity | 393 | invalid_document | 0.1506 | PASS |
| external-entity | 407 | invalid_document | 0.3812 | PASS |
| duplicate-document | 706 | unsafe_archive | 0.1318 | PASS |
| path-traversal | 566 | unsafe_archive | 0.1447 | PASS |
| embedded-macro | 595 | active_content | 0.1689 | PASS |
| missing-document | 23 | invalid_document | 0.1396 | PASS |

压缩用例实际2 MiB重复字节压入2616B的DOCX容器，因真实展开体积/压缩比上限拒绝；不解压到业务目录。有效对照实际解析合成段落。七个恶意/损坏容器均以returncode2、ok=false及预期code返回，无parsed结果，内部合成marker未出现在错误；相对路径/父目录escape.xml均不存在。DTD/entity、宏、重复项和穿越各自走实际拒绝路径，外部entity不交予Office读取器。

私有`.runtime/baichuan-ai-local/night-acceptance-20261018/office-attack-containers/receipt.json` SHA256 `68717a815a9bd8bbaaa8352c1ece0ad7802f4ac22545b2378cdef0a988bd4308`。每案保存source.docx、result.json、stderr.txt；5个解析源码执行前后SHA一致。脚本`check_office_attack_containers.py`另行保留。业务库/HTTP/模型/前端/服务操作0。此项不替代HTTP附件上传全流程、网页提示注入、实际Markdown渲染或全部日志泄漏验收，AI-AC15其余缺口保留。
