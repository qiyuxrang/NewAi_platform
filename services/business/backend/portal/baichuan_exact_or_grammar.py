"""Consume a complete two-grade exact OR request, or defer to the model.

This grammar supplies intent only. Certificate truth, missing data, permissions,
sources and qualification ordering still belong to the shared rule engine.
"""
import re

from .baichuan_conditions import ConditionError, compile_conditions
from .baichuan_local_grammar import ALIAS_PATTERN, GRADES
from .baichuan_models import QUALIFICATION_GRADES
from .baichuan_rules_aliases import canonical_category


REQUEST = re.compile(
    rf'(?:投标人(?:须|必须)具备|请查询|请查找|查询|查找|检索|找)?'
    rf'(?P<first>{ALIAS_PATTERN})(?:精确)?(?P<g1>[一二三四五1-5])级'
    rf'(?:或者|或)(?P<second>{ALIAS_PATTERN})?(?:精确)?(?P<g2>[一二三四五1-5])级'
    r'(?:[，,](?:二者任一即可|任一即可))?'
    r'(?:[；;]只输出(?:企业名称|企业名|名称)和(?:联系电话|电话)[，,]最多(?P<limit>[0-9]{1,4})家)?'
    r'[。！!]?', re.IGNORECASE)


def extract(text, *, revision, today, text_ref):
    if (not isinstance(text, str) or not 0 < len(text) <= 1000
            or not isinstance(text_ref, str) or not text_ref.startswith('message:')):
        return None
    match = REQUEST.fullmatch(re.sub(r'\s+', '', text))
    if match is None:
        return None
    category = canonical_category(match['first'].upper() if match['first'].isascii() else match['first'])
    if match['second']:
        alias = match['second'].upper() if match['second'].isascii() else match['second']
        if canonical_category(alias) != category:
            return None
    grades = [GRADES.get(match[key], match[key]) for key in ('g1', 'g2')]
    if category not in QUALIFICATION_GRADES or any(g not in QUALIFICATION_GRADES[category] for g in grades):
        return None
    limit = int(match['limit']) if match['limit'] else 20
    if not 1 <= limit <= 5000:
        return None
    try:
        return compile_conditions({'schema_version': 1, 'revision': revision,
            'source_refs': [text_ref], 'as_of': {'date': today.isoformat(), 'basis': 'query_date'},
            'must': {'any': [{'field': 'qualification', 'category': category,
                'holder': 'bidder', 'op': 'grade_exact', 'value': grade,
                'source_refs': [text_ref]} for grade in grades]},
            'should': [], 'unresolved': [], 'output': {'fields': ['name', 'phone'], 'limit': limit}}, today=today)
    except (ConditionError, TypeError, ValueError, AttributeError):
        return None
