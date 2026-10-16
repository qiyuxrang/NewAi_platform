import { useState } from 'react'
import { ArrowLeft, BadgeCheck, Building2, Cloud, Copy, ExternalLink, FileText, Globe, Hammer, Landmark, Layers3, Lightbulb, Mail, MapPin, Network, Pencil, Phone, Settings, Settings2, ShieldCheck, Trophy, Users } from 'lucide-react'
import { qualificationLabel, safeWebsite, websiteType } from './Baichuan-data'
import type { CompanyDetailData } from './Baichuan-data'
import heroArchitecture from './assets/baichuan/hero-architecture.png'
import businessArchitecture from './assets/baichuan/business-architecture.png'
import businessLighting from './assets/baichuan/business-lighting.png'
import businessNetwork from './assets/baichuan/business-network.png'
import businessPark from './assets/baichuan/business-park.png'
import businessCity from './assets/baichuan/business-city.png'
import businessIot from './assets/baichuan/business-iot.png'
import ksznkjLogo from './assets/baichuan/ksznkj-logo.png'

const qualificationIcons = { electronic: Building2, labor: Hammer, cs: BadgeCheck, cmmi: Settings, ccrc: ShieldCheck, itss: Settings2, security: ShieldCheck }
const businessVisuals = [
  [/园区/, Building2, businessPark],
  [/物联/, Cloud, businessIot],
  [/照明|亮化/, Lightbulb, businessLighting],
  [/智慧城市|城市/, Landmark, businessCity],
  [/网络|系统集成|计算机/, Network, businessNetwork],
  [/建筑|智能化|电子/, Building2, businessArchitecture],
] as const

function value(text: string | null | undefined) {
  const content = text || ''
  const parts = []
  let cursor = 0
  for (const match of Array.from(content.matchAll(/https?:\/\/[^\s<>"'`，。；：！？、（）【】「」『』《》〈〉“”‘’…—]+/gi))) {
    const start = match.index
    if (start > 0 && /[\w+.:/\\@%-]/.test(content[start - 1])) continue
    let label = match[0]
    let previous
    do {
      previous = label
      label = label.replace(/[.,;:!?]+$/, '')
      for (const [open, close] of [['(', ')'], ['[', ']'], ['{', '}']]) {
        if (label.endsWith(close) && label.split(close).length > label.split(open).length) label = label.slice(0, -1)
      }
    } while (label !== previous)
    const href = safeWebsite(label)
    if (!href) continue
    parts.push(content.slice(cursor, start), <a key={start} className="bc-source-link" href={href} target="_blank" rel="noopener noreferrer">{label}</a>)
    cursor = start + label.length
  }
  parts.push(content.slice(cursor))
  return parts
}
export default function CompanyDetail({ data, matched, onBack, onEdit }: { data: CompanyDetailData; matched: Set<string>; onBack: () => void; onEdit: () => void }) {
  const { company, qualifications, people, permissions } = data
  const website = safeWebsite(company.website)
  const homepage = websiteType(company.website_kind)
  const [copyStatus, setCopyStatus] = useState({ url: '', message: '' })
  const importedDescription = company.description?.startsWith('源表资质声明') ? company.description : null
  const description = importedDescription ? null : company.description
  const overview = description?.split('\n').filter(line => !line.trim().startsWith('业务领域：')).join('\n').trim()
  const businessAreas = description?.split('\n').find(line => line.trim().startsWith('业务领域：'))?.trim().slice(5).split(/[、；;]+/).map(item => item.trim().replace(/[。.]$/, '')).filter(Boolean) || []
  const region = [company.province, company.city].filter(Boolean).join(' · ')
  const contacts = ([['业务联系人', company.contact_name], ['业务联系电话', company.contact_phone], ['公司电话', company.phone], ['邮箱', company.email]] as const).filter(([, text]) => text?.trim())
  const hasOverview = !!(overview || company.address?.trim() || region)
  const hasContacts = !!(contacts.length || company.address?.trim() || website)
  const sources = [
    { label: '原始资质声明', text: importedDescription },
    { label: '公司资料', text: company.source },
    ...qualifications.map(item => ({ label: qualificationLabel(item, true), text: item.source })),
    ...people.map(item => ({ label: item.name, text: item.source })),
  ].filter(item => item.text?.trim())
  return <div className="bc-company-detail">
    <div className="bc-detail-toolbar"><button type="button" className="bc-link" onClick={onBack}><ArrowLeft size={16}/>返回公司列表</button><span>›</span><span>企业详情</span>{permissions.can_edit && <button className="bc-button" onClick={onEdit}><Pencil size={16}/>编辑资料</button>}</div>
    <header className="bc-company-hero bc-card">
      <div className="bc-hero-main">
        <img className="bc-hero-architecture" src={heroArchitecture} alt="" aria-hidden="true"/>
        <div className="bc-company-identity"><div className="bc-company-mark">{company.name === '陕西凯笙信息技术有限公司' ? <img src={ksznkjLogo} alt="陕西凯笙信息技术有限公司标识"/> : <Building2 size={58} strokeWidth={1.5} aria-hidden="true"/>}</div><div><h1>{company.name}</h1>{overview ? <p className="bc-hero-intro">{overview}</p> : region && <p className="bc-hero-region"><MapPin size={16}/>{region}</p>}</div></div>
        {!!qualifications.length && <div className="bc-hero-tags">{qualifications.map((item, index) => <span key={item.id || index} data-category={item.category}>{qualificationLabel(item)}</span>)}</div>}
      </div>
      <aside className="bc-website-panel" aria-label={homepage.label}><div className="bc-website-heading"><Globe size={30}/><div><span>{homepage.label}</span>{website && <a className="bc-official-address" href={website} target="_blank" rel="noopener noreferrer">{new URL(website).host}</a>}</div></div>{website ? <a className="bc-button bc-primary" href={website} target="_blank" rel="noopener noreferrer"><ExternalLink size={17}/>{homepage.action}</a> : <button type="button" className="bc-button bc-primary" disabled title="添加官网地址后可访问"><ExternalLink size={17}/>{homepage.action}</button>}{website ? <button className="bc-button" onClick={async () => { try { await navigator.clipboard.writeText(website); setCopyStatus({ url: website, message: '官网链接已复制' }) } catch { setCopyStatus({ url: website, message: '复制失败，请手动复制上方网址' }) } }}><Copy size={17}/>{homepage.code === 'corporate' ? '复制官网链接' : '复制主页链接'}</button> : permissions.can_edit && <button type="button" className="bc-button" onClick={onEdit}><Pencil size={17}/>添加官网地址</button>}{website && copyStatus.url === website && <p className="bc-copy-status" role="status">{copyStatus.message}</p>}</aside>
    </header>
    {(hasOverview || qualifications.length > 0 || businessAreas.length > 0 || hasContacts) && <div className="bc-detail-columns">
      {hasOverview && <section className="bc-card bc-overview-card"><div className="bc-detail-section-heading"><span><FileText size={20}/></span><h2>企业概览</h2><small>COMPANY OVERVIEW</small></div>{overview && <p className="bc-overview-text">{value(overview)}</p>}{(region || company.address?.trim()) && <div className="bc-overview-facts">{region && <div><MapPin size={26}/><div><span>所在地区</span><strong>{region}</strong></div></div>}{company.address?.trim() && <div><Building2 size={26}/><div><span>公司地址</span><strong>{company.address}</strong></div></div>}</div>}</section>}
      {!!qualifications.length && <section className="bc-card bc-qualifications-card"><div className="bc-detail-section-heading"><span><Trophy size={20}/></span><h2>核心资质</h2><small>QUALIFICATIONS</small></div><div className="bc-qualification-grid">{qualifications.map((item, index) => { const Icon = qualificationIcons[item.category]; return <article className="bc-detail-record" data-category={item.category} key={item.id || index}><Icon size={27} aria-hidden="true"/><div><h3>{qualificationLabel(item, true)}{item.id && matched.has(item.id) && <span className="bc-hit">命中筛选</span>}</h3>{(item.certificate_no || item.valid_until) && <dl className="bc-details">{item.certificate_no && <div><dt>证书编号</dt><dd>{item.certificate_no}</dd></div>}{item.valid_until && <div><dt>有效期至</dt><dd>{item.valid_until}</dd></div>}</dl>}</div></article> })}</div></section>}
      {!!businessAreas.length && <section className="bc-card bc-business-card"><div className="bc-detail-section-heading"><span><Layers3 size={20}/></span><h2>业务领域</h2><small>BUSINESS AREAS</small></div><div className="bc-business-grid">{businessAreas.map(area => { const visual = businessVisuals.find(([pattern]) => pattern.test(area)); const Icon = visual?.[1] || Layers3; return <div key={area}>{visual && <img src={visual[2]} alt="" aria-hidden="true" loading="lazy"/>}<span className="bc-business-icon"><Icon size={28} aria-hidden="true"/></span><strong>{area}</strong></div> })}</div></section>}
      {hasContacts && <section className="bc-card bc-contacts-card"><div className="bc-detail-section-heading"><span><Phone size={20}/></span><h2>联系方式</h2><small>CONTACT INFORMATION</small></div><dl className="bc-contact-list">{contacts.map(([label, text]) => <div key={label}>{label === '邮箱' ? <Mail size={19}/> : label === '业务联系人' ? <Users size={19}/> : <Phone size={19}/>}<dt>{label}</dt><dd>{value(text)}</dd></div>)}{company.address?.trim() && <div><MapPin size={19}/><dt>公司地址</dt><dd>{company.address}</dd></div>}{website && <div><Globe size={19}/><dt>{homepage.label}</dt><dd><a className="bc-source-link" href={website} target="_blank" rel="noopener noreferrer">{website}</a></dd></div>}</dl></section>}
    </div>}
    {!!people.length && <section className="bc-card bc-people-card"><div className="bc-detail-section-heading"><span><Users size={20}/></span><h2>公开人员资料</h2></div><div className="bc-records">{people.map((item, index) => <article className="bc-detail-record" key={item.id || index}><h3>{item.name}</h3><dl className="bc-details">{([['岗位', item.position], ['部门', item.department], ['专业方向', item.specialties], ['职称认证', item.credentials], ['代表项目 / 成果', item.achievements], ['已知汇报关系', item.reports_to_text]] as const).filter(([, text]) => text?.trim()).map(([label, text]) => <div key={label}><dt>{label}</dt><dd>{value(text)}</dd></div>)}</dl></article>)}</div></section>}
    {!!sources.length && <section className="bc-card bc-provenance"><details className="bc-source-details"><summary>资料来源</summary>{sources.map((item, index) => <div className="bc-source" key={index}><h3>{item.label}</h3><div>{value(item.text)}</div></div>)}</details></section>}
  </div>
}
