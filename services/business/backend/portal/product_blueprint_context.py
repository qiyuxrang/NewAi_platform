"""Lossless project facts for guide-scope calls; no retrieval or model inference."""

from copy import deepcopy


def scope_context(context, base):
    """Keep source order and all item values, sharing only repeated field names.

    ``items.rows[i]`` maps to ``context.items[i]`` using ``items.columns``.
    Missing cells use null plus an explicit missing-column index, so an absent
    field stays distinguishable from an original null. Background is verbatim;
    its existing source/block labels and character offsets remain usable.
    """
    result = deepcopy(context)
    items = context.get("items", [])
    columns = sorted({key for item in items for key in item})
    result["items"] = {
        "source_path": "/items", "columns": columns,
        "rows": [[deepcopy(item.get(key)) for key in columns] for item in items],
        "missing": [[index, [column for column, key in enumerate(columns) if key not in item]]
                    for index, item in enumerate(items) if any(key not in item for key in columns)],
    }
    # Knowledge is writing reference, never evidence of this project's scope.
    # This matches the persisted retrieval identity/status contract; no body is copied.
    identity_fields = (
        "id", "provider", "chunk_id", "dataset_id", "document_id", "title", "url",
        "sha256", "retrieved_at", "query_hash", "fact_scope", "reference_only", "untrusted",
        "source_trust", "timeliness", "content_kind", "content_truncated", "applicability", "status",
    )
    result["knowledge_sources"] = {
        "source_path": "/knowledge_sources", "role": "reference_only_not_project_facts",
        "rows": [{key: deepcopy(source[key]) for key in identity_fields if key in source}
                 for source in context.get("knowledge_sources", [])],
    }
    result["scope_policy"] = (
        "items.columns与rows按位置对应，rows[i]来自原context.items[i]（索引从0开始）；"
        "missing记录[行索引,[缺失列索引]]，其余null均为原值。所有设备行和业务字段完整保留，未按名称筛选。"
        "background、project、requirements、conditions、statements逐字保留；"
        "背景中的资料/内容块标记及字符偏移指向原文，sources原样保留来源身份和未知状态。"
        "knowledge_sources.rows[i]仅为原知识来源[i]的身份与状态，正文已排除，不构成项目范围或项目事实。"
        "另行提供的基础目录base章节仅属于模型推断线索，不能反向证明项目事实。"
        "否定、限定、负数、歧义和待确认状态均须保留；缺少事实应判pending，不得因未出现关键词而判not_applicable。"
    )
    return result
