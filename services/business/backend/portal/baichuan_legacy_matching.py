"""Owner-confirmed legacy catalog facts; no inference about new public claims."""
from datetime import date


def trusted_legacy_verdict(node, facts, compiled, rule, certificates):
    if ('trusted_legacy_qualifications' not in facts or node['holder'] != 'bidder'
            or node.get('scope') or rule.get('standard')):
        return None
    # The owner confirmed the current catalog, not an unrecorded historical or
    # future certificate interval. Full certificate evidence may still handle it.
    if (compiled['as_of']['basis'] != 'query_date'
            or compiled['as_of']['date'] != facts.get('legacy_trust_date')):
        return None
    rows = [q for q in facts['trusted_legacy_qualifications'] if q['category'] == node['category']]
    present = [q for q in rows if q['status'] == 'PRESENT']
    if present and any(q['status'] == 'ABSENT' for q in rows):
        return {'verdict': 'conflict', 'evidence_ids': [], 'reason': '旧资质库同类别同时记载持有和未持有，需消除记录冲突。'}
    if node['op'] == 'grade_at_least':
        accepted = rule.get('at_least', {}).get(node['value'])
        if not accepted:
            return None
    else:
        accepted = [node['value']]
    matching = [q for q in present if node['op'] == 'present' or q['grade'] in accepted]
    for q in matching:
        if q['valid_until'] and date.fromisoformat(q['valid_until']) < date.fromisoformat(compiled['as_of']['date']):
            continue
        # Do not use an owner-approved old entry to mask a known current conflict,
        # suspension, or explicit contrary date recorded for that same grade.
        contrary = False
        for c in certificates:
            if (c['holder_type'] != 'bidder' or str(c['holder_company_id']) != str(facts['id'])
                    or c['grade'] != q['grade'] or c['verification_status'] == 'superseded'):
                continue
            if c['verification_status'] == 'conflict' or c['revocation_status'] in {'revoked', 'suspended'}:
                contrary = True
            if c.get('valid_until') and c['valid_until'] < compiled['as_of']['date']:
                contrary = True
            if c.get('valid_from') and c['valid_from'] > compiled['as_of']['date']:
                contrary = True
        if not contrary:
            return {'verdict': 'satisfied', 'evidence_ids': list(q.get('evidence_ids', [])),
                    'reason': f'按用户确认的旧资质库记录匹配：{q["category"]} / {q["grade"] or "已具备"}；'
                              f'资质记录 {q["id"]}。未执行新的联网核验。'}
    if not present and any(q['status'] == 'ABSENT' for q in rows):
        if any(c['assertion_status'] == 'PRESENT' and c['verification_status'] != 'superseded'
               and c['holder_type'] == 'bidder' and str(c['holder_company_id']) == str(facts['id'])
               for c in certificates):
            return {'verdict': 'conflict', 'evidence_ids': [], 'reason': '旧库明确未持有与新增证书记录冲突。'}
        return {'verdict': 'failed', 'evidence_ids': [], 'reason': '用户确认的旧资质库明确记录未持有该类别。'}
    return None
