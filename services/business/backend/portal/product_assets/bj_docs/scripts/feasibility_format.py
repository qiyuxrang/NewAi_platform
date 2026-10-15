"""User-requested Yulin March 2024 feasibility layout; no design approval implied."""
from copy import deepcopy
import hashlib
from pathlib import Path
import re

from lxml import etree as E
from ooxml import NS, q

GUIDE_SOURCE_SHA256 = '1ffe2ace313aa4dc76e90ef9f2b91df6e1a2f0d3ef7896dfa9bb0ce2ab89be84'
BODY_END_BOOKMARK = 'YulinFeasibilityBodyEnd'


def ensure(parent, name):
    found = parent.find(name, NS)
    if found is None:
        found = E.SubElement(parent, q(name))
    return found


def value(parent, name, val):
    ensure(parent, name).set(q('w:val'), str(val))


def font(properties, name, size, bold=False, english=None):
    fonts = ensure(properties, 'w:rFonts')
    for key in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'):
        fonts.attrib.pop(q('w:' + key), None)
    for key in ('ascii', 'hAnsi', 'cs'):
        fonts.set(q('w:' + key), english or name)
    fonts.set(q('w:eastAsia'), name)
    value(properties, 'w:sz', round(size * 2)); value(properties, 'w:szCs', round(size * 2))
    value(properties, 'w:b', int(bold)); value(properties, 'w:bCs', int(bold))
    value(properties, 'w:snapToGrid', 0)


def typography(node, *, name='宋体', size=12, bold=False, align='both', line=360,
               before=0, after=0, indent=0, left_chars=0, english='Times New Roman'):
    pp = node.find('w:pPr', NS)
    if pp is None:
        pp = E.Element(q('w:pPr')); node.insert(0, pp)
    for tag in ('w:numPr', 'w:ind', 'w:pBdr', 'w:framePr', 'w:tabs', 'w:contextualSpacing'):
        for old in pp.findall(tag, NS):
            pp.remove(old)
    spacing = ensure(pp, 'w:spacing')
    spacing.attrib.clear()
    for key, val in (('before', before * 20), ('after', after * 20), ('line', line), ('lineRule', 'auto')):
        spacing.set(q('w:' + key), str(val))
    value(pp, 'w:jc', align); value(pp, 'w:snapToGrid', 0)
    ind = ensure(pp, 'w:ind')
    ind.set(q('w:left'), str(round(left_chars * size * 20)))
    ind.set(q('w:right'), '0')
    ind.set(q('w:firstLine'), str(round(indent * size * 20)))
    ind.set(q('w:firstLineChars'), str(indent * 100))
    if left_chars:
        ind.set(q('w:leftChars'), str(left_chars * 100))
    font(ensure(pp, 'w:rPr'), name, size, bold, english)
    for run in node.findall('.//w:r', NS):
        props = run.find('w:rPr', NS)
        if props is None:
            props = E.Element(q('w:rPr')); run.insert(0, props)
        # Preserve explicitly authored emphasis in ordinary prose.
        prior_bold = props.find('w:b', NS)
        use_bold = bold or (name == '宋体' and size == 12 and prior_bold is not None
                           and prior_bold.get(q('w:val'), '1') not in ('0', 'false'))
        font(props, name, size, use_bold, english)


def format_paragraph(node, role):
    if role == 'appendix':
        typography(node, name='黑体', size=16, align='left', line=240, before=6, after=6, english=None)
        value(node.find('w:pPr', NS), 'w:outlineLvl', 0)
    elif role.startswith('heading'):
        level = int(role[-1])
        spec = {1: (22, 18), 2: (18, 12), 3: (16, 6), 4: (14, 6)}[level]
        typography(node, name='黑体' if level < 4 else '宋体', size=spec[0], bold=level in (1, 4),
                   align='center' if level == 1 else 'left', line=240,
                   before=spec[1], after=spec[1], english=None)
        pp = node.find('w:pPr', NS)
        for old in pp.findall('w:pStyle', NS):
            pp.remove(old)
        value(pp, 'w:outlineLvl', level - 1)
        value(pp, 'w:keepNext', 1); value(pp, 'w:keepLines', 1)
    elif role in ('figure_and_table_caption', 'table_caption'):
        typography(node, name='黑体', align='center', english=None)
        value(node.find('w:pPr', NS), 'w:keepNext', int(role == 'table_caption'))
    elif role == 'figure':
        typography(node, align='center', line=240, before=6, after=3)
        value(node.find('w:pPr', NS), 'w:keepNext', 1)
    else:
        typography(node, indent=2)
    return node


def normalize_section(section):
    size = ensure(section, 'w:pgSz')
    landscape = size.get(q('w:orient')) == 'landscape' or int(size.get(q('w:w'), '11906')) > int(size.get(q('w:h'), '16838'))
    size.set(q('w:w'), '16838' if landscape else '11906')
    size.set(q('w:h'), '11906' if landscape else '16838')
    size.set(q('w:orient'), 'landscape' if landscape else 'portrait')
    margins = ensure(section, 'w:pgMar')
    for key, mm in (('top', 25.4), ('bottom', 25.4), ('left', 31.8), ('right', 31.8),
                    ('header', 15), ('footer', 17.5), ('gutter', 0)):
        margins.set(q('w:' + key), str(round(mm * 1440 / 25.4)))
    for old in section.findall('w:docGrid', NS):
        section.remove(old)


def field(paragraph, instruction, result='1'):
    for kind, text in (('begin', None), ('instr', instruction), ('separate', None), ('text', result), ('end', None)):
        run = E.SubElement(paragraph, q('w:r'))
        if kind in ('begin', 'separate', 'end'):
            node = E.SubElement(run, q('w:fldChar')); node.set(q('w:fldCharType'), kind)
        elif kind == 'instr':
            node = E.SubElement(run, q('w:instrText')); node.text = text
            node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        else:
            E.SubElement(run, q('w:t')).text = text


def paragraph(text='', **spec):
    node = E.Element(q('w:p'))
    if text:
        E.SubElement(E.SubElement(node, q('w:r')), q('w:t')).text = text
    typography(node, **spec)
    return node


def spacer(points):
    node = paragraph('', size=1)
    spacing = node.find('w:pPr/w:spacing', NS)
    spacing.set(q('w:line'), str(points * 20)); spacing.set(q('w:lineRule'), 'exact')
    return node


def table_layout(table, landscape):
    width = round((250 if landscape else 160) * 1440 / 25.4)
    props = ensure(table, 'w:tblPr')
    ensure(props, 'w:tblW').attrib.update({q('w:w'): str(width), q('w:type'): 'dxa'})
    value(props, 'w:jc', 'center')
    ensure(props, 'w:tblLayout').set(q('w:type'), 'fixed')
    for old in props.findall('w:tblpPr', NS):
        props.remove(old)
    columns = table.findall('w:tblGrid/w:gridCol', NS)
    original = [int(col.get(q('w:w'), '1')) for col in columns]
    if columns:
        widths = [round(width * item / max(sum(original), 1)) for item in original]
        widths[-1] += width - sum(widths)
        for col, target in zip(columns, widths):
            col.set(q('w:w'), str(target))
    else:
        widths = []
    for index, row in enumerate(table.findall('w:tr', NS)):
        rp = ensure(row, 'w:trPr')
        height = ensure(rp, 'w:trHeight'); height.set(q('w:val'), str(round(7 * 1440 / 25.4)))
        height.set(q('w:hRule'), 'atLeast')
        for old in rp.findall('w:tblHeader', NS):
            rp.remove(old)
        if index == 0:
            value(rp, 'w:tblHeader', 1)
        column = 0
        for cell in row.findall('w:tc', NS):
            cp = ensure(cell, 'w:tcPr')
            span = cp.find('w:gridSpan', NS)
            count = int(span.get(q('w:val'), '1')) if span is not None else 1
            if widths:
                ensure(cp, 'w:tcW').attrib.update({q('w:w'): str(sum(widths[column:column + count])), q('w:type'): 'dxa'})
            column += count
            for p in cell.findall('.//w:p', NS):
                typography(p, size=10.5, line=240)


def paragraph_style(doc, style_id, name, sample):
    """Reuse the template's built-in TOC style and its existing references."""
    styles = doc.styles.element
    style = None
    if re.fullmatch(r'TOC[1-3]', style_id):
        style = next((item for item in styles.findall('w:style', NS)
                      if item.get(q('w:type')) == 'paragraph' and item.find('w:name', NS) is not None
                      and item.find('w:name', NS).get(q('w:val'), '').casefold() == name.casefold()), None)
    if style is None:
        style = next((item for item in styles.findall('w:style', NS)
                      if item.get(q('w:styleId')) == style_id), None)
    if style is None:
        style = E.SubElement(styles, q('w:style'))
    else:
        style_id = style.get(q('w:styleId'))
    style.attrib.clear()
    style.attrib.update({q('w:type'): 'paragraph', q('w:styleId'): style_id})
    for child in list(style):
        style.remove(child)
    value(style, 'w:name', name)
    pp = deepcopy(sample.find('w:pPr', NS))
    rp = pp.find('w:rPr', NS)
    if rp is not None:
        pp.remove(rp)
    style.append(pp)
    if rp is not None:
        style.append(rp)


def apply_format(doc, data, bookmark_map):
    """Replace only template front matter; keep authored OOXML nodes intact."""
    body = doc.element.body
    authored_names = set(bookmark_map.values())
    first = next(node for node in body if any(mark.get(q('w:name')) in authored_names
                 for mark in node.findall('.//w:bookmarkStart', NS)))
    for node in list(body)[:list(body).index(first)]:
        body.remove(node)
    terminal = body.find('w:sectPr', NS)
    if terminal is None:
        raise ValueError('feasibility body section required')
    for section in body.findall('.//w:sectPr', NS):
        normalize_section(section)
        for name in ('w:headerReference', 'w:footerReference', 'w:titlePg', 'w:pgNumType'):
            for old in section.findall(name, NS):
                section.remove(old)
    template_section = deepcopy(terminal)
    ensure(template_section, 'w:pgSz').attrib.update({q('w:w'): '11906', q('w:h'): '16838', q('w:orient'): 'portrait'})
    title = re.sub(r'\s*[-—·]?\s*[（(]?(?:可行性研究报告|可研报告|可行性研究|可研)[）)]?\s*$', '', data['metadata']['title']).strip() or data['metadata']['title']
    company, date = data['metadata']['organization'], data['metadata']['date']
    front = [spacer(90), paragraph(title, name='黑体', size=26, align='center', line=240, english=None),
              paragraph('可行性研究报告', name='黑体', size=26, align='center', line=240, english=None)]
    front.append(spacer(270))
    for text in ('项目建设单位：待提供', '编制单位：' + company, '编制日期：' + date,
                 '项目建设单位联系人：待提供', '联系方式：待提供'):
        front.append(paragraph(text, name='黑体', size=16, align='left', left_chars=4, english=None))
    pagebreak = paragraph('')
    E.SubElement(E.SubElement(pagebreak, q('w:r')), q('w:br')).set(q('w:type'), 'page')
    front.append(pagebreak)
    for text, signature in (('编制单位：' + company, '（盖章）'), ('编制单位负责人：待提供', '（签章）'),
                            ('编制单位项目负责人：待提供', '（职称）'), ('主要编制人员：待提供', '（职称）'),
                            ('参加编制单位：待提供', '（盖章）')):
        front.append(paragraph(text, size=16, align='left', line=240, left_chars=2, english=None))
        front.append(paragraph('', size=16, line=240))
        front.append(paragraph(signature, size=16, align='left', line=240, left_chars=2, english=None))
        front.append(paragraph('', size=16, line=240))
    def section_break():
        p = paragraph('', size=1, line=20)
        section = deepcopy(template_section)
        value(section, 'w:type', 'nextPage')
        p.find('w:pPr', NS).append(section)
        return p
    front += [section_break(), paragraph('目  录', name='黑体', size=16, bold=True, align='center', english=None)]
    toc = paragraph('')
    field(toc, ' TOC \\o "1-3" \\h \\z \\u ', '目录待更新')
    typography(toc)
    front += [toc, section_break()]
    for index, node in enumerate(front):
        body.insert(index, node)
    # The footer total is the last decimal body page, including landscape sections.
    ids = [int(mark.get(q('w:id'), '0')) for mark in body.findall('.//w:bookmarkStart', NS)]
    tail = next((node for node in reversed(list(body)) if node.tag == q('w:p')), None)
    if tail is None:
        tail = paragraph(''); body.insert(len(body) - 1, tail)
    if body.findall('.//w:bookmarkStart[@w:name="' + BODY_END_BOOKMARK + '"]', NS):
        raise ValueError('reserved feasibility end bookmark already exists')
    start = E.SubElement(tail, q('w:bookmarkStart')); start.set(q('w:id'), str(max(ids, default=0) + 1)); start.set(q('w:name'), BODY_END_BOOKMARK)
    end = E.SubElement(tail, q('w:bookmarkEnd')); end.set(q('w:id'), start.get(q('w:id')))
    for name in ('w:evenAndOddHeaders', 'w:mirrorMargins'):
        for old in doc.settings.element.findall(name, NS):
            doc.settings.element.remove(old)
    for index, section in enumerate(doc.sections):
        normalize_section(section._sectPr)
        section.header.is_linked_to_previous = False
        section.footer.is_linked_to_previous = False
        for story in (section.header, section.footer):
            for child in list(story._element):
                story._element.remove(child)
        header = E.SubElement(section.header._element, q('w:p'))
        footer = E.SubElement(section.footer._element, q('w:p'))
        if index == 0:
            # User's cover sample has a single rule; the title leaf stays blank.
            section.different_first_page_header_footer = True
            story = section.first_page_header
            story.is_linked_to_previous = False
            for child in list(story._element):
                story._element.remove(child)
            cover_header = paragraph(title, size=10.5, align='right', line=240, english=None)
            story._element.append(cover_header)
            border = ensure(ensure(cover_header.find('w:pPr', NS), 'w:pBdr'), 'w:bottom')
            border.attrib.update({q('w:val'): 'single', q('w:sz'): '4', q('w:space'): '1', q('w:color'): '000000'})
            section.first_page_footer.is_linked_to_previous = False
            for child in list(section.first_page_footer._element):
                section.first_page_footer._element.remove(child)
            E.SubElement(section.first_page_footer._element, q('w:p'))
        if index:
            header.append(paragraph(title, size=10.5, align='right', line=240, english=None)[-1])
            typography(header, size=10.5, align='right', line=240, english=None)
            # The guide does not replace the user's existing body-header rule.
            border = ensure(ensure(header.find('w:pPr', NS), 'w:pBdr'), 'w:bottom')
            border.attrib.update({q('w:val'): 'double', q('w:sz'): '8', q('w:space'): '1', q('w:color'): '000000'})
            numbering = ensure(section._sectPr, 'w:pgNumType')
            numbering.set(q('w:fmt'), 'upperRoman' if index == 1 else 'decimal')
            if index in (1, 2):
                numbering.set(q('w:start'), '1')
            if index == 1:
                field(footer, ' PAGE ', 'I')
            else:
                footer.append(paragraph('第')[-1]); field(footer, ' PAGE ')
                footer.append(paragraph('页/共')[-1]); field(footer, ' PAGEREF ' + BODY_END_BOOKMARK + ' \\h ')
                footer.append(paragraph('页')[-1])
            typography(footer, size=10.5, align='center', line=240, english=None)
    # Explicit TOC styles remove inherited exact spacing, tabs and heading numbering.
    for level in range(1, 4):
        p = paragraph(''); typography(p)
        pp = p.find('w:pPr', NS)
        tabs = ensure(pp, 'w:tabs'); tab = E.SubElement(tabs, q('w:tab'))
        tab.attrib.update({q('w:val'): 'right', q('w:leader'): 'dot', q('w:pos'): str(round(146.4 * 1440 / 25.4))})
        paragraph_style(doc, 'TOC' + str(level), 'toc ' + str(level), p)
    # Word copies direct heading character formatting into TOC results. Put the
    # specified heading appearance in a style so TOC1-3 can govern refreshed text.
    for block in data['blocks']:
        if block['type'] != 'heading':
            continue
        role = 'appendix' if block['text'].startswith('附录') else 'heading' + str(block['level'])
        style_id = 'YulinFeasibility' + role.title()
        paragraph_style(doc, style_id, 'Yulin Feasibility ' + role, format_paragraph(E.Element(q('w:p')), role))
        name = bookmark_map[block['id']]
        node = next(p for p in body.findall('w:p', NS) if any(mark.get(q('w:name')) == name
                    for mark in p.findall('w:bookmarkStart', NS)))
        pp = node.find('w:pPr', NS)
        for old in pp.findall('w:rPr', NS) + pp.findall('w:pStyle', NS):
            pp.remove(old)
        style_ref = E.Element(q('w:pStyle')); style_ref.set(q('w:val'), style_id); pp.insert(0, style_ref)
        for run in node.findall('.//w:r', NS):
            for old in run.findall('w:rPr', NS):
                run.remove(old)
    section = doc.sections[2]._sectPr
    for node in list(body)[len(front):]:
        if node.tag == q('w:tbl'):
            table_layout(node, ensure(section, 'w:pgSz').get(q('w:orient')) == 'landscape')
        ending = node.find('w:pPr/w:sectPr', NS)
        if ending is not None:
            sections = list(doc.sections)
            position = next(i for i, item in enumerate(sections) if item._sectPr is ending)
            if position + 1 < len(sections):
                section = sections[position + 1]._sectPr
    return {'guide_source_sha256': GUIDE_SOURCE_SHA256,
            'format_renderer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'guide_format_status': 'user_requested_yulin_202403',
            'format_policy_status': 'user_requested_yulin_202403', 'toc_depth': 3,
            'company_identity': {'name': company, 'logo_used': False},
            'unverified_items': ['Word pagination, TOC and PAGEREF refresh and page image inspection required',
                                 'Engineering assertions require independent professional review',
                                 'Unknown construction and signatory identities remain pending provision']}
