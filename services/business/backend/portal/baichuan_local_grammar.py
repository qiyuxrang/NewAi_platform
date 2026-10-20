"""Closed text grammar: consume the whole request or leave it to the model.

This is a parser, never a source of company facts or qualification ordering.
No files, network, database or model calls belong here.
"""
from copy import deepcopy
import re

from .baichuan_conditions import ConditionError, compile_conditions
from .baichuan_models import QUALIFICATION_GRADES
from .baichuan_rules_aliases import ALIASES


# Deliberately small, unambiguous vocabulary. Other locations use the model.
REGIONS = {
    '广东省': ('company.province', '广东省', None),
    '广东': ('company.province', '广东省', None),
    '陕西省': ('company.province', '陕西省', None),
    '陕西': ('company.province', '陕西省', None),
    '广州市': ('company.city', '广州市', '广东省'),
    '广州': ('company.city', '广州市', '广东省'),
    '榆林市': ('company.city', '榆林市', '陕西省'),
    '榆林': ('company.city', '榆林市', '陕西省'),
    '西安市': ('company.city', '西安市', '陕西省'),
    '西安': ('company.city', '西安市', '陕西省'),
}
REGION_PATTERN = '|'.join(re.escape(x) for x in sorted(REGIONS, key=len, reverse=True))
ALIAS_PATTERN = '|'.join(re.escape(x) for x in sorted(ALIASES, key=len, reverse=True))
QUALIFICATION = re.compile(
    rf'(?P<alias>{ALIAS_PATTERN})(?:精确)?(?P<grade>[一二三四五1-5])级', re.IGNORECASE)
GRADES = dict(zip('一二三四五', '12345'))


def _region_node(alias, text_ref):
    field, value, _ = REGIONS[alias]
    return {'field': field, 'op': 'eq', 'value': value, 'source_refs': [text_ref]}


def _safe_previous(previous):
    if (previous['should'] or previous['unresolved'] or previous['as_of']['basis'] != 'query_date'
            or not previous['source_refs']
            or any(not ref.startswith('message:') for ref in previous['source_refs'])):
        return False

    def safe(node):
        if 'all' in node:
            return all(safe(child) for child in node['all'])
        if 'any' in node or 'not' in node:
            return False
        if (not node.get('source_refs')
                or any(ref not in previous['source_refs'] for ref in node['source_refs'])
                or set(node) & {'scope', 'rule_version'}):
            return False
        if node['field'].startswith('company.'):
            return node['op'] == 'eq'
        return (node['holder'] == 'bidder' and node['op'] == 'grade_exact'
                and node['category'] in QUALIFICATION_GRADES
                and node['value'] in QUALIFICATION_GRADES[node['category']])

    return safe(previous['must'])


def _leaves(node):
    if 'all' in node:
        return [leaf for child in node['all'] for leaf in _leaves(child)]
    return [node]


def extract(text, *, previous=None, revision, today, text_ref):
    """Return a validated tree only for a fully recognized positive sentence."""
    if (not isinstance(text, str) or not 0 < len(text) <= 1000
            or not isinstance(text_ref, str) or not text_ref.startswith('message:')):
        return None
    # Whitespace is formatting; punctuation/words are consumed by explicit rules.
    sentence = re.sub(r'\s+', '', text)
    sentence = re.sub(r'[。！!]$', '', sentence)
    try:
        if previous is not None:
            tree = compile_conditions(previous, today=today)
            if not _safe_previous(tree):
                return None
            follow = re.fullmatch(rf'只要(?P<region>{REGION_PATTERN})的[，,]?加上电话', sentence)
            if sentence != '加上电话' and follow is None:
                return None
            tree = deepcopy(tree)
            if follow:
                alias = follow['region']
                field, value, province = REGIONS[alias]
                nodes = _leaves(tree['must'])
                if any(node['field'] == field and node['value'] != value for node in nodes):
                    return None
                if province and any(node['field'] == 'company.province' and node['value'] != province for node in nodes):
                    return None
                if field == 'company.province' and any(
                        node['field'] == 'company.city' and (
                            node['value'] not in REGIONS or REGIONS[node['value']][2] != value)
                        for node in nodes):
                    return None
                tree['must'] = {'all': [tree['must'], _region_node(alias, text_ref)]}
            if 'phone' not in tree['output']['fields']:
                tree['output']['fields'].append('phone')
            tree['revision'] = revision
            tree['source_refs'] = list(dict.fromkeys([*tree['source_refs'], text_ref]))
            return compile_conditions(tree, today=today)

        # A fresh query cannot be a follow-up or a partial extraction.
        sentence = re.sub(r'^(?:请查询|请查找|找出|查找|检索|查询|找)', '', sentence, count=1)
        sentence = re.sub(r'(?:的企业|企业|公司)$', '', sentence, count=1)
        nodes = []
        region = re.match(rf'(?P<region>{REGION_PATTERN})(?:的)?', sentence)
        if region:
            nodes.append(_region_node(region['region'], text_ref))
            sentence = sentence[region.end():]
        categories = set()
        cursor = 0
        for _ in range(6):
            matched = QUALIFICATION.match(sentence, cursor)
            if matched is None:
                return None
            alias = matched['alias']
            category = ALIASES.get(alias) or ALIASES.get(alias.upper())
            grade = GRADES.get(matched['grade'], matched['grade'])
            if (category not in QUALIFICATION_GRADES or grade not in QUALIFICATION_GRADES[category]
                    or category in categories):
                return None
            categories.add(category)
            nodes.append({'field': 'qualification', 'category': category, 'holder': 'bidder',
                          'op': 'grade_exact', 'value': grade, 'source_refs': [text_ref]})
            cursor = matched.end()
            if cursor == len(sentence):
                break
            separator = re.match(r'并且|且|和', sentence[cursor:])
            if separator is None:
                return None
            cursor += separator.end()
            if cursor == len(sentence):
                return None
        if cursor != len(sentence):
            return None
        return compile_conditions({'schema_version': 1, 'revision': revision,
            'source_refs': [text_ref], 'as_of': {'date': today.isoformat(), 'basis': 'query_date'},
            'must': nodes[0] if len(nodes) == 1 else {'all': nodes}, 'should': [], 'unresolved': [],
            'output': {'fields': ['name', 'phone'], 'limit': 20}}, today=today)
    except (ConditionError, KeyError, TypeError):
        return None
