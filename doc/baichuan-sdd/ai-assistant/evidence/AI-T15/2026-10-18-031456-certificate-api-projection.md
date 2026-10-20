# AI-T14 / AI-T15：证书快照元数据的页面响应收口

时间：2026-10-18T03:14:56.464618+08:00。新代码尚未加载所属服务。0真实库访问、0外部模型/网络、0前端/服务操作；测试仅新建隔离文件SQLite和临时storage。

[只读审计](2026-10-18-031059-security-interface-readonly.md)发现新certificate_records会由results原样返回页面，而当前页面不消费。Root确认并在327项全回归结束后授权最小兼容修正，原冻结运行未被中途修改。该327项实际PASS180.549秒/0skip代表修正前版本，不能冒称已覆盖新API。

## 改动

仅修改 `baichuan_assistant_api.py` 与 `test_baichuan_integration_review.py`。API将每个页面结果行浅拷贝，仅剔除certificate_records后响应；保留其他键值，不原地pop，不修改数据库快照。matching与exports实现及对应测试保持上一轮指纹。XLSX仍从固定snapshot.results读取证号记录；旧快照兼容行为不变。

此投影消除该额外字段的页面传输和状态保存，但Django加载完整JSON快照后分页的既有内存边界仍在；本单元未声称解决全库JSON存储大小或总体P95问题。

## 实际检查

```text
.runtime/company-test/python/Scripts/python.exe scripts/baichuan/check_backend.py portal.tests.test_baichuan_assistant portal.tests.test_baichuan_exports portal.tests.test_baichuan_matching portal.tests.test_baichuan_integration_review
```

结果 **70 tests /52.616秒 /OK /0skip**；system check 0 issues。新增一项 `test_result_api_omits_export_only_certificate_metadata_without_mutating_snapshot_or_xlsx`，实际通过Django GET响应断言：

- 所有旧结果键值保持，响应完全不包含certificate_records。
- 数据库重新读取后完整冻结记录保留，不因API读取被删除。
- 同一快照真实生成候选XLSX并用openpyxl读回K8证号001239，类型s、主体manufacturer、核实状态未核实。
- 导出后再次重读快照仍完全相同。

该测试是隔离API/文件链路，不是新真实浏览器下载。其余69项为相关实际回归；不与此前327或58项相加。两Python文件py_compile及git diff --check均退出0。

## 恢复点

私有 `night-acceptance-20261018/certificate-api-projection/targeted.log`、`receipt.json`：

- API SHA `14f16b1ac85aafb546ea68f7941921b04b3802d19f78d9e25244e0d08c33fbfc`
- integration测试 SHA `ea44ca68507085023183d073fd16e6b1ea61a65a5409a0fa9ad93388a69040ca`
- 日志 SHA `035ae7c2e1bce7011dc491852251569388928fdde2756b034f3695b8b8f2fd39`
- 收据 SHA `99033f39c11d9a89c7dcea936e062045d56f006160c9bd07837296b9a67d8000`

相对root冻结327项输入，仅API和该测试两文件变化。代码再次冻结，交root安排最终全部24模块回归与backend-only加载；主checkpoint/progress/tasks/acceptance未由本代理修改。AI-AC14/15攻击载荷或完整权限矩阵的缺口不因这项兼容修正而自动放行。
