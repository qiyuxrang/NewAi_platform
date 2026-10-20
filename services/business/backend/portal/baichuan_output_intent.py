"""Whole-message output edits and positive composite requests; no company facts.

Only fully consumed author text is handled. Documents, pending gates and model
fallback remain owned by the orchestrator. This module never reads storage.
"""
from copy import deepcopy
import re

from .baichuan_conditions import ConditionError, compile_conditions
from .baichuan_local_grammar import extract as simple_request
from .baichuan_exact_or_grammar import extract as exact_or

FIELDS = {'企业名称': ['name'], '企业名': ['name'], '名称': ['name'],
          '联系电话': ['phone'], '电话': ['phone'], '官网': ['website'],
          '邮箱': ['email'], '地址': ['address'], '省份': ['province'],
          '城市': ['city'], '地区': ['province', 'city'], '统一社会信用代码': ['credit_code']}
FIELD_PATTERN = '|'.join(re.escape(value) for value in sorted(FIELDS, key=len, reverse=True))
FIELD_LIST = rf'(?:{FIELD_PATTERN})(?:(?:和|及|、)(?:{FIELD_PATTERN}))*'
NUMBER = r'(?:最多|前|只看前|只要前)(?P<limit>[0-9]{1,4})(?:家|条)'
ADD_FIELDS = rf'(?:加上|增加|补充)(?P<fields>{FIELD_LIST})'


def _sentence(text):
    if not isinstance(text, str) or not 0 < len(text) <= 1000:
        return None
    return re.sub(r'[。！!]$', '', re.sub(r'\s+', '', text))


def output_edit(text, previous_output):
    """Return an explicit output spec, consuming every remaining character."""
    sentence = _sentence(text)
    if not sentence:
        return None
    sentence = re.sub(r'^保留(?:附件全部硬性要求和优先项|前轮全部条件|原有条件|之前条件)[，,；;]', '', sentence, count=1)
    parts = re.split(r'[，,；;]', sentence)
    if len(parts) == 2 and any(re.fullmatch(NUMBER, parts[index])
            and re.fullmatch(ADD_FIELDS, parts[1-index]) for index in (0, 1)):
        output = output_edit(parts[0], previous_output)
        return output_edit(parts[1], output) if output is not None else None
    match = re.fullmatch(rf'(?:(?:只输出|只显示|列出)(?P<fields>{FIELD_LIST})[，,]?)?{NUMBER}', sentence)
    fields_only = re.fullmatch(rf'(?:只输出|只显示|列出)(?P<fields>{FIELD_LIST})', sentence)
    add = re.fullmatch(ADD_FIELDS, sentence)
    if not (match or fields_only or add):
        return None
    result = deepcopy(previous_output)
    if match:
        limit = int(match['limit'])
        if not 1 <= limit <= 5000:
            return None
        result['limit'] = limit
    field_text = (match or fields_only or add)['fields'] if (not match or match['fields']) else None
    if field_text:
        fields = [field for name in re.split(r'和|及|、', field_text) for field in FIELDS[name]]
        result['fields'] = list(dict.fromkeys([*result['fields'], *fields] if add else ['name', *fields]))
    return result


def edit_previous(text, previous, *, revision, today, text_ref):
    if not isinstance(text_ref, str) or not text_ref.startswith('message:'):
        return None
    try:
        tree = compile_conditions(previous, today=today)
        if tree['unresolved'] or not tree['source_refs']:
            return None
        output = output_edit(text, tree['output'])
        if output is None:
            return None
        tree['output'], tree['revision'] = output, revision
        tree['source_refs'] = list(dict.fromkeys([*tree['source_refs'], text_ref]))
        return compile_conditions(tree, today=today)
    except (ConditionError, KeyError, TypeError, ValueError):
        return None


def _positive(text, *, revision, today, text_ref):
    options = dict(revision=revision, today=today, text_ref=text_ref)
    result = simple_request(text, **options) or exact_or(text, **options)
    if result is not None:
        return result
    # Explicit conjunction only. Never split aliases containing the word 和,
    # or invent precedence for mixed conjunction/disjunction expressions.
    parts = re.split(r'[，,]?(?:并且|且)', text)
    if not 2 <= len(parts) <= 6 or any(not part for part in parts):
        return None
    children = []
    for part in parts:
        child = simple_request(part, **options) or exact_or(part, **options)
        if child is None:
            return None
        # Mixed conjunction/disjunction requests continue through the model;
        # a fast path must not invent the user's Boolean precedence.
        if 'any' in child['must']:
            return None
        children.append(child['must'])
    base = deepcopy(child)
    base['must'] = {'all': children}
    return compile_conditions(base, today=today)


def extract_request(text, *, revision, today, text_ref):
    """Positive first query with a fully recognized output suffix."""
    sentence = _sentence(text)
    if not sentence or not isinstance(text_ref, str) or not text_ref.startswith('message:'):
        return None
    try:
        for separator in re.finditer(r'[，,；;]', sentence):
            output = output_edit(sentence[separator.end():], {'fields': ['name', 'phone'], 'limit': 20})
            if output is None:
                continue
            tree = _positive(sentence[:separator.start()], revision=revision, today=today, text_ref=text_ref)
            if tree is not None:
                tree['output'] = output
                return compile_conditions(tree, today=today)
        return None
    except (ConditionError, KeyError, TypeError, ValueError):
        return None
