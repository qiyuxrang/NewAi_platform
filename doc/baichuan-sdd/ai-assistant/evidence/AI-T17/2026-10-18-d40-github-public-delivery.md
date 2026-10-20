# AI-T17 / AI-D40 GitHub 公开交付

状态：代码和企业数据已实际推送并从 GitHub 校验通过。

用户显式同意现有公开仓库及企业数据公开；目标为 `qiyuxrang/NewAi_platform` 的 `codex/baichuan-delivery-20261018` 分支。本轮实际调用 GitHub API 核对登录身份/仓库公开性/推送权限；远端main与本地起点均为 `ef1676cd8327d693dab897c45a234ba91413884e`。根目录不存在 GitHub Actions 工作流；交付使用独立分支，不进入正式部署。

数据文件见 [快照说明](../../../../../data/baichuan/README.md)、[真实校验](../../../../../data/baichuan/validation.json) 及 [清单](../../../../../data/baichuan/manifest.json)。9表25843行、1283企业、1460旧资质、1622证书、4064来源路径/1754去重归档通过逐行摘要、内部关联、原始来源解压哈希、CSV计数及全部文件哈希校验。保留外部actor/job审计引用，排除其用户/任务行，未制造可运行历史任务。

只读导出，未更改现用数据库/前端/服务，未补全、联网研究、调用模型或再次核验旧资质。已有D38/D39功能证据保留，本轮不是重跑617项/16项。新增导出器以本次真实导出及独立回读验收。

候选文件逐一检查既有实际凭据、会话/密码哈希及高置信密钥格式，输出只含路径和计数。首次检测含token_parameter/api_key_env元数据及明确合成安全测试标记，已准确限定为非秘密元数据/该唯一测试字面量；未删改应用或测试来绕扫描。真实秘密字节仍检查。原始FAIL与最终PASS保存于本机 `.runtime/baichuan-ai-local/github-delivery/`。

实际发布版本：`1afd65ddd8bf02962bad624f51a04062a186c168`；分支 [codex/baichuan-delivery-20261018](https://github.com/qiyuxrang/NewAi_platform/tree/codex/baichuan-delivery-20261018)。已从GitHub完整递归树逐一验证2178个发布路径的Git对象ID，1768数据文件均与工作区原始字节对应。实际从GitHub官方Git Blob API下载并解码7个文件：企业/旧资质/人员JSONL、manifest、validation及原Excel/网页gzip归档，逐字节一致。其他数据文件由完整Git对象ID逐一绑定原字节，未冒充全部下载。远端main仍为原起点。详见 [发布收据](2026-10-18-d40-publication-receipt.json)。

新增数据导出/校验通过，模型0、写库0，前端163当前指纹、5所属进程、原企业及资质/任务/模型/来源/导出数据、源表和试运行库均与本单元基线一致。本次数据新增字节保留属性，避免跨平台换行破坏快照哈希。CSV保留企业原文中的尾空格；完整staged差异检查还保留7个既有文件的历史空白警告，其中助手文件和旧测试输入不能为清洁差异而变更；排除这7个原样保留文件后的新增交付文件差异检查实际通过，未将全量检查冒报PASS。

恢复点：代码及数据已发布；收尾文档在同一分支追加。无部署、补全或前端变更待执行，不因上传自动启动这些工作。

远端回读过程保留原始失败：首次整仓树传输中断后采用目录树及gzip传输；首次公开提交的四个文本数据被Git自动换行转换，实际字节核对发现后用`git add --renormalize data/baichuan`追加修正提交，未改源数据。`raw.githubusercontent.com` DNS不可用，改用GitHub官方Git Blob API；大文件额外下载有中断，不以其计为通过，最终采用全数据对象校验与7个明确成功的真实回读。最终PASS仅绑定修正后的发布版本。
