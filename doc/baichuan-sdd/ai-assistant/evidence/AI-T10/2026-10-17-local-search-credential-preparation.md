# AI-T10 本机搜索凭据准备

日期：2026-10-17。范围：仅后端本地配置工具、临时目录测试与脚本 README；不修改前端、共享 SDD 状态、local_dev 或业务 provider，不执行搜索/模型/SQL，不创建账号或采购服务。

## 实施契约与采用范围

根代理授权在用户已有密钥路径到达后准备 Tavily / Brave 配置。只复用仓内 `portal/product_web_search.py:configuration`：`PRODUCT_WEB_SEARCH_PROVIDER`、`PRODUCT_WEB_SEARCH_TOKEN_ENV`，对应 `TAVILY_API_KEY` / `BRAVE_API_KEY`。该单元没有新增第三方代码或依赖；provider 的官方资格、计费和质量校验由后续有界验证处理，本单元不宣称服务可用。

`scripts/baichuan/local_search.py` 默认 `status`，只读所属环境标记及非敏感状态；不加载 Django 或凭据正文。显式 `configure --provider tavily|brave --key-file PATH` 验证 10–512 字符的单行可打印 ASCII（允许末尾一次 LF/CRLF），保留原用户文件，拒绝任何已有目的配置。

固定 owned runtime 是本仓 `.runtime/baichuan-ai-local`，校验既有 environment kind；逐级拒绝 symlink 和 Windows reparse point。新文件独占创建，在任何密钥字节写入前，通过实际 `whoami /user` SID 配置当前用户 ACL，不依赖可能不准确的 USERNAME。凭据仅存 ignored `search-credentials.json`；`search-link.json` 固定 `enabled=false / quality_not_validated`，输出不包含 token、前缀或哈希。新建状态失败时撤回本次新建的凭据，不改旧用户文件。

`backend_search_environment` 仅接受 portal / baichuan-worker，当前只提供关闭的环境及非敏感 provider/token-env 名称，不读取或释放密钥；没有 activate，未接常驻服务。通过质量门禁及受控激活均是后续单元，不把“配置完成”当作“真实可用”。

## 实测与边界

使用现有 company-test Python 3.13，仅临时目录和合成 token：

```text
.runtime/company-test/python/Scripts/python.exe -m unittest discover -s scripts/baichuan/tests -p test_local_search.py -v
首次：11 tests / 0.569s / OK，无 skip。
补充未知 JSON marker 与有界读取后：11 tests / 0.567s / OK，无 skip。
真实 owned runtime 默认 status：configured=false / provider=null / enabled=false / quality_not_validated。
git diff --check：通过。
```

测试覆盖两 provider 认证字段、真实当前用户 Windows ACL 去继承、合法 CRLF、非法多行/空白/非 ASCII/长度/控制符、未知所属环境、reparse 拒绝、已有文件不覆盖、状态不读取凭据、默认无新 Django/portal/sqlite/socket/urllib 导入或 subprocess 调用、禁止 gateway/frontend helper、状态失败清除本次新建凭据及 CLI 无激活入口。生产凭据没有读取或保存；未创建真实 owned 搜索配置。

未验收：真实认证、搜索质量、计费、质量门禁激活、常驻服务集成。研究覆盖与字段核实无变化。工具拒绝未知配置时保留文件，由后续维护操作明确处理，不能靠重复 configure 覆盖。
