# AI-T16 真实 OCR 边界、双并发与临时 SQLite 锁竞争

2026-10-17，工作区 HEAD `ef1676cd8327d693dab897c45a234ba91413884e` 加本轮未提交实现。先复查 AI-T02 及 [8项文件容量边界](2026-10-17-file-capacity.md)，本次补旋转、模糊、加密、损坏及资源项，不重复原有100/101页等用例。

仅新增本证据和 [独立探针](probe_ocr_edges.py)，没有修改核心 parser、业务测试、前端、部署配置或服务。无实际企业库、真实模型或公网访问；没有安装依赖。

## 可重复命令与隔离

仓库根目录运行，`--output` 必须为 `.runtime` 内尚不存在的目录，其父目录须存在：

```powershell
.runtime/company-test/python/Scripts/python.exe doc/baichuan-sdd/ai-assistant/evidence/AI-T16/probe_ocr_edges.py --output .runtime/baichuan-ai-local/night-acceptance-20261017/ocr-edges-final
```

本轮此路径已经存在，复现须换新的输出目录，探针拒绝覆盖。最终命令实际退出 **0**，7个场景断言全部通过，`complete=true`。脚本 SHA256 `748c7d7092dc5fed4285b935ccdf3dca8dc5fe9220ba7e6ab0aee76d623a6323`。

父进程最长180秒；单个真实解析子进程90秒。父超时仅结束本次新建探针及其子树，不涉及常驻服务。复用原 `product_intake.run_parser`、凭据白名单沙箱、两槽 `BoundedSemaphore`、OCR及页/块/字数限额。Python主进程 socket/DNS 禁止；真实 parser 子进程也自行禁用网络。清除继承环境后，Django默认连接指向本次临时目录的未创建文件，结束断言从未打开；直接SQLite竞争另用同临时目录的 `synthetic-lock.sqlite3`，不运行迁移或创建企业。

私有最终收据、6个合成PDF及PNG均在上述输出目录。`receipt.json` SHA256 `57314ebe70f22d0679626bfdaacac8ede8846092930331986c2bd190972c1739`。完整正文仅为明确虚构的验收句，含“投标人须具备 ITSS 二级”和“制造商 ISO9001 仅为优先项”，无企业名录或联系人。旋转、重模糊、清晰页及已知密码解锁后的加密页PNG已实际打开检查；损坏PDF按设计无法渲染。没有用文字层替代扫描OCR。

## 真实结果

| 场景 | 实际返回与断言 | 秒 |
| --- | --- | ---: |
| 单页扫描图旋转90° | `needs_review/ocr`；3块、56字，页1+bbox；识别出 `ITSS二级` 和完整制造商优先项；`ocr_review_required`，不因高置信度声称已核实 | 2.2113 |
| 单页 GaussianBlur radius=8 重模糊 | `failed/ocr`，0块/0字；`image_no_text` 定位页1及 `no_text`；不从清晰样本或上下文补字 | 1.7128 |
| AES-256、非空用户密码的PDF，不向parser提供密码 | 明确拒绝 `encrypted_document`，提示“PDF 已加密或损坏，请解密后重新上传。” | 0.2426 |
| 有 `%PDF-1.7` 头但结构损坏 | 明确拒绝 `invalid_document`，同类可操作提示，不伪造正文 | 0.2586 |
| 第一个真实三页扫描OCR任务 | `needs_review/ocr`，9块/164字，页1–3均有bbox及逐页核对警告 | 5.6823 |
| 同时启动的第二个真实三页扫描OCR任务 | 同上；真实子进程重叠，进程内最多2个parser任务 | 5.7360 |
| 两槽实际占用时的第三次请求 | `parser_busy`，明确“当前资料解析繁忙，请稍后重试；文件尚未重复保存。”；没有第三个parser进程 | 0.0038 |

这是每场景一个样本，不计算P95。未执行模型语义理解；输出中的投标人/制造商句仅证明OCR文本及位置，不能把本实验当成资质主体推理或证书核验通过。

## 资源观察与限制

Windows venv的 `Scripts/python.exe` 是重定向启动器，单读其进程会把OCR资源误记为约4MB。因此最终探针用 ToolHelp32 枚举本次parser进程的后代，读取真实解释器的 `GetProcessMemoryInfo` 和 `GetProcessTimes`；不遍历或计入已有服务。每100ms采样整棵parser子树，同时保存各进程峰值工作集/页文件用量及CPU秒。

- 实测单进程峰值工作集 **468779008字节（447.062MiB）**。
- 实测同时运行子树的工作集总和采样峰值 **871292928字节（830.930MiB）**。工作集含共享页，求和会重复计共享内存；100ms采样也可能漏过短峰，不能称精确私有内存或硬上限。
- 现有限额：20MiB输入、8MiB输出、100页、12个OCR页、2400万图像像素；parser父进程两槽；每子进程OMP/OpenBLAS/MKL最多2线程，OCR intra-op=2/inter-op=1。本机Windows路径没有POSIX `resource` CPU/文件限制，也**没有强制RSS上限**，仅有有界输入/输出/页数、并发和wall timeout。没有据实测峰值捏造内存限额。
- 两槽是每个业务Python进程的限制，不是跨任意多个服务进程的全机信号量；本次没有以此宣称多服务全局最多两个OCR。

## 与OCR同时的真实SQLite竞争

OCR组运行期间，持有者对临时库执行 `BEGIN IMMEDIATE`、增量更新后保持事务。另一个写者以200ms SQLite busy timeout尝试，实际 **290.1ms** 后收到 `database is locked`，没有无限重试。只读连接在锁内 **0.8ms** 读取到原已提交值0，不看到未提交写入。

OCR完成释放锁，持有者总事务 **5.7421秒** 后提交；第二写者仅再试一次，**4.0ms** 完成。最终值恰为2、两个唯一事件各一条，`PRAGMA quick_check=ok`，无丢失/重复更新。这验证当前SQLite锁/有限失败/解锁恢复，**不替代业务worker的租约/fence/队列并发测试**，后者已有独立进程测试证据。最终所有直接SQLite连接关闭，parser暂存为空，整个临时库目录删除，Django数据库始终未打开。

## 版本、过程与未覆盖项

Windows 11 `10.0.26200`；外层Python3.13.16、SQLite3.53.1、Django5.2.18、pypdf6.20.0、Pillow12.3.0、PyMuPDF1.28.2。真实OCR解释器沿用 `.runtime/company-test/cloud-ocr/Scripts/python.exe`，另一次本地metadata只读确认 RapidOCR1.4.4、onnxruntime1.30.0、pypdfium2 5.13.0、numpy2.5.3、Pillow12.3.0。PyMuPDF仅生成/渲染虚构fixture，未成为新增生产依赖；已有AGPL/商业许可说明继续见AI-T02，无第三方代码复制或新安装。

首轮 `ocr-edges-r1` 确已跑完场景，但探针未显式关闭 `with sqlite3.connect()` 对象，临时库清理未完成，退出1、`complete=false`，不计通过；原收据/原暂存失败目录保留在ignored `.runtime`。同时发现只量启动器不能代表OCR内存，已改为观测真实子树。修正探针后 `ocr-edges-r2` 完整退出0；追加明确字面提取和模糊零正文断言、父超时子树终止后，以当前最终脚本再跑 `ocr-edges-final` 退出0。r1/r2/最终三轮不是独立测试项，数量不相加。

未覆盖：实际部署多工作进程的全机OCR限流/硬内存隔离；长时间负载稳定性和真实尾延迟；所有旋转角度/渐变模糊/真实复杂招标版式；实际浏览器扫描文件提示；实际模型的条款主体/等级关系质量；真实服务器资源竞争。这里只补AI-AC04/AI-AC17的隔离文件/资源子项，不据此放行AI-T16整项、实际部署或全库资料核实。
