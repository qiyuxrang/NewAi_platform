import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
const require = createRequire(import.meta.url)
let playwright
try { playwright = require('playwright') } catch { playwright = require('C:/Users/BJRunner/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright') }
const base = process.env.SDD_BROWSER_URL || 'http://127.0.0.1:3080'
const output = resolve(process.env.SDD_BROWSER_EVIDENCE_DIR || `doc/implementation-evidence/browser-run-${new Date().toISOString().replace(/[:.]/g,'-')}`)
mkdirSync(output, { recursive: true })
let diagnosticPage
const evidence = { environment: 'Chromium, isolated intercepted API fixtures; no requests passed to business backend', viewportChecks: [], interactions: [], ledgerChecks: [], navigationChecks: [], reportChecks: [], failures: [], apiCalls: [] }
const task = { id:'sdd-check-project',title:'验收样例 · 数字化项目',state:'DRAFT',stage:'INPUT',version:1,updated_at:'2026-10-14T01:00:00Z',created_at:'2026-10-14T01:00:00Z',input_version:1,blueprint_version:0,input:{project:'验收样例',requirements:'隔离浏览器验收',items:[],background:'',conditions:[]},blueprint:null,blueprint_approved:false,blueprint_review:{revision_count:0,revision_limit:3,revisions_remaining:3},chapters:[],reports:[],artifacts:[],sources:[],approvals:[],issues:[],error_code:'',actions:[],blockers:{},reviewer_id:null,owner_id:77,input_issues:[],impact:{},output_families:['technical-solution','feasibility','presentation'] }
const record = {project_id:'PS-check',project_name:'验收样例 · 售前项目',owner:'样例负责人',status:'',amount:'',follow_up_date:'',project_progress:'已沟通建设范围，下一步核对资料。',description:'保留完整原字段',client_contact:'对接人甲',project_type:'集成',maturity:'待核对',source_sheet:'Sheet7',source_row:'8',source_group:'商机',source_sequence:'3',source_amount:'25',amount_unit:'万元',follow_up_history:'原有跟进记录',notes:'原始备注',annual_plan:'下月继续跟进',expected_signing:'2026年11月'}
const presalesFields={project_id:'项目编号',project_name:'项目名称',owner:'负责人',status:'状态',amount:'预计金额',follow_up_date:'跟进时间',project_progress:'项目进展',description:'项目概况',client_contact:'甲方对接人',project_type:'项目定型',maturity:'成熟度',source_sheet:'来源工作表',source_row:'来源行',source_group:'来源分组',source_sequence:'来源序号',source_amount:'原始额度',amount_unit:'原表单位',follow_up_history:'跟进记录',notes:'备注',annual_plan:'推进计划',expected_signing:'预计签约时间'}
const engineeringFields={project_id:'项目编号',project_name:'项目名称',owner:'负责人',status:'状态',planned_end:'计划完成日期',progress:'完成进度'}
const makeLedger=department=>({department,state:'draft',revision:7,as_of:'2026-10-14',source_name:'隔离验收样例',records:department==='presales'?[{...record}]:[{project_id:'EG-check',project_name:'验收样例 · 工程项目',owner:'工程负责人',status:'实施中',planned_end:'2026-11-30',progress:'35.50'}],fields:department==='presales'?presalesFields:engineeringFields,statuses:department==='presales'?['线索','需求沟通','方案编制','报价','商务谈判','已赢单','已丢单']:['待开工','实施中','待验收','整改中','已验收','质保中','已结束'],permissions:{can_edit:true,can_submit:true,can_publish:true},updated_at:'2026-10-14T01:00:00Z',updated_by:{id:77,name:'验收员工'},last_return_reason:''})
const board=(source=false,q='')=>({department:'finance',title:'财务部看板',available:true,snapshot_id:'isolated',fields:{project_id:'项目编号',project_name:'项目名称',client_name:'业主单位',contract_amount:'合同金额',received_amount:'已收金额',opening_receivable:'年初应收',receivable_balance:'应收结余',owner:'回款负责人',current_status:'目前状态',due_date:'应收日期',source_sheet:'来源工作表'},statuses:[],metrics:source?[{key:'contract',label:'合同金额',value:'300',unit:'元'},{key:'opening_receivable',label:'年初应收',value:null,unit:'元'},{key:'received',label:'1—7月回款',value:'100',unit:'元'},{key:'receivable',label:'应收结余',value:'200',unit:'元'},{key:'planned',label:'8—12月计划',value:null,unit:'元'}]:[{key:'contract',label:'合同金额',value:q?'100':'300',unit:'元'},{key:'received',label:'已收金额',value:q?'20':'100',unit:'元'},{key:'receivable',label:'待收金额',value:q?'80':'200',unit:'元'},{key:'overdue',label:'逾期待收',value:'0',unit:'元'}],distribution:source?[{label:'主体甲',count:1},...q?[]:[{label:'主体乙',count:1}]]:[{label:'未结清',count:q?1:2}],records:[{project_id:'F1',project_name:'验收样例 · 甲项目',client_name:'业主甲',contract_amount:'100',received_amount:'20',due_date:'',opening_receivable:'',receivable_balance:'80',owner:'负责人甲',current_status:'待核对',source_sheet:source?'应收总账':''},...q?[]:[{project_id:'F2',project_name:'验收样例 · 乙项目',client_name:'业主乙',contract_amount:'200',received_amount:'80',receivable_balance:'120',due_date:''}]],total:2,filtered_count:q?1:2,currency:'CNY',scope:'仅当前账号授权范围内已发布数据',source:{name:'隔离验收样例',as_of:'2026-10-14',imported_at:'2026-10-14T01:00:00Z',kind:'published_ledger',revision:7,state:'published'}})
const manager={id:'isolated-manager',username:'验收总经理',role:'user',business_role:'general_manager',department_code:null,portal_user_id:77,capabilities:['general_manager','product','engineering','hr']}
const financeEmployee={...manager,id:'isolated-finance',username:'验收财务员工',business_role:'employee',department_code:'finance',capabilities:['finance']}
const financeId='00000000-0000-4000-8000-000000000001'
const hrRequest={id:'hr-check',created_by_id:77,position_name:'验收岗位',headcount:1,responsibilities:'核对需求',required_requirements:'项目经验',preferred_requirements:'',education_requirement:'',experience_requirement:'',skill_requirements:[],work_location:'陕西',notes:'',input_version:1,current_jd_id:'jd-check',official_jd_id:'jd-check',official_jd_stale:false,missing_items:[],created_at:'2026-10-14T01:00:00Z',updated_at:'2026-10-14T01:00:00Z'}
const hrJd={id:'jd-check',request_id:hrRequest.id,version:1,input_version:1,body:'验收岗位职责\n核对项目需求及来源证据。',state:'confirmed',channel:'general',stale:false,source_jd_id:null}
const hrResult={id:'resume-check',filename:'验收简历.pdf',processing_status:'completed',error_code:'',size:1024,score:80,unknown_count:0,hard_gap_count:0,stale:false,rule_version:'fixture',matrix:[{id:'requirement-check',text:'项目经验',verdict:'MATCH',evidence:[{quote:'负责项目资料核对',locator:'第1页'}]}]}
const hrBatch={id:'batch-check',position_name:hrRequest.position_name,jd_version_id:hrJd.id,jd_version:1,version:1,status:'completed',stale:false,total:1,completed:1,failed:0,pending:0,prescreened:0,progress:100,updated_at:'2026-10-14T01:00:00Z',artifacts:[hrResult]}
function financeFixture(source=false){
 const own={project_id:'FN-own',project_name:'本人财务项目',contract_amount:'100',received_amount:'20',due_date:'',client_name:'业主甲',owner:'催收人甲',current_status:'待核对',contract_type:'集成',affiliate:'挂靠甲',billing_entity:'主体甲',source_row:source?'8':''}
 if(source)Object.assign(own,{source_sheet:'应收总账',opening_receivable:'',receivable_balance:'80',...Object.fromEntries(Array.from({length:12},(_,i)=>[`${i<7?'received':'planned'}_${String(i+1).padStart(2,'0')}`,i===0?'10':'']))})
 const records=[own,{...own,project_id:'FN-other',project_name:'他人财务项目'},{...own,project_id:'FN-unknown',project_name:'归属未知财务项目'}]
 const ledger={department:'finance',state:'draft',revision:7,as_of:'2026-10-14',source_name:source?'隔离财务源表样例':'手工录入',records,record_meta:{[financeId]:{project_id:'FN-own',record_author_id:77,draft_actor_id:77,draft_revision:7,draft_checksum:'a'.repeat(64),deleted:false},'00000000-0000-4000-8000-000000000002':{project_id:'FN-other',record_author_id:88,draft_actor_id:88,draft_revision:7,draft_checksum:'a'.repeat(64),deleted:false}},fields:Object.fromEntries(Object.keys(own).map(key=>[key,key])),permissions:{can_edit:true,can_submit:false,can_publish:false}}
 return {ledger,published:{id:'00000000-0000-4000-8000-000000000003',department:'finance',state:'published',revision:3,as_of:ledger.as_of,source_name:ledger.source_name,records:[{...own,current_status:'原已发布状态'},records[1]],record_meta:{[financeId]:{...ledger.record_meta[financeId],draft_revision:3,draft_checksum:'b'.repeat(64)}}}}
}
async function session(user=manager,options={}) {
 const context=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true,serviceWorkers:'block',reducedMotion:options.reduced?'reduce':'no-preference'})
 await context.addInitScript(()=>{localStorage.setItem('openclaw_access_token','isolated-browser-token');window.__sddEvents=[];addEventListener('popstate',event=>{window.__sddEvents.push({href:location.href,state:history.state});setTimeout(()=>window.__sddEvents.push({afterHref:location.href,afterState:history.state}),50)},true)})
 const state={user,grant:options.grant!==false,source:false,financeError:0,conflict:false,finance:financeFixture(options.financeSource),ledger:{presales:makeLedger('presales'),engineering:makeLedger('engineering')},writes:[],unexpected:[],pageErrors:[]}
 await context.route('**/api/**', async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname.replace('/api/enterprise/business/','/api/'),method=request.method()
  evidence.apiCalls.push({path:url.pathname,query:url.search,method})
  const json=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
  if(path==='/api/auth/me')return json(state.user)
  if(path==='/api/enterprise/status')return json({configured:true,linked:true,available:true,message:'隔离验收连接'})
  if(path==='/api/openclaw/ping')return json({message:'ok'})
  if(path==='/api/openclaw/events/stream')return route.fulfill({status:204})
  if(path==='/api/openclaw/container/info')return json({status:'running'})
  if(path==='/api/business/ledgers/permissions/')return json({departments:state.grant?[...Object.entries(state.ledger).map(([department,ledger])=>({department,...ledger.permissions})),{department:'finance',...state.finance.ledger.permissions}]:[]})
  const fm=path.match(/^\/api\/business\/ledgers\/finance\/(.*)$/)
  if(fm){const suffix=fm[1],{ledger}=state.finance
   if(state.financeError)return json({detail:'财务权限已撤销'},state.financeError)
   if(method==='GET'){
    if(suffix==='')return json(ledger)
    if(suffix==='versions/')return json({department:'finance',versions:[{id:state.finance.published.id,revision:state.finance.published.revision,state:'published'}]})
    if(suffix===`versions/${state.finance.published.id}/`)return json(state.finance.published)
   }
   const body=request.postDataJSON();state.writes.push({path,method,body});assert.equal(body.expected_revision,ledger.revision);assert.equal(ledger.permissions.can_edit,true)
   if(state.conflict){state.conflict=false;ledger.revision++;ledger.records[0].billing_entity='并发更新主体';return json({detail:'台账版本冲突'},409)}
   if(suffix.startsWith('records/')){
    assert.deepEqual(Object.keys(body).sort(),['expected_revision','record']);const id=decodeURIComponent(suffix.slice(8).replace(/\/$/,''))
    if(id){assert.equal(method,'PUT');const row=ledger.records.find(item=>item.project_id===id);assert.ok(row);const meta=Object.values(ledger.record_meta).find(item=>item.project_id===id);assert.equal(meta?.record_author_id,77);assert.ok(Object.keys(row).every(key=>key in body.record));Object.assign(row,body.record);Object.assign(meta,{draft_actor_id:77,draft_revision:ledger.revision+1,draft_checksum:'c'.repeat(64)})}
    else{assert.equal(method,'POST');assert.equal(body.record.source_sheet,undefined);ledger.records.push(body.record);const id=crypto.randomUUID();ledger.record_meta[id]={project_id:body.record.project_id,record_author_id:77,draft_actor_id:77,draft_revision:ledger.revision+1,draft_checksum:'d'.repeat(64),deleted:false}}
    ledger.state='draft'
   }else if(suffix==='publish/'){
    assert.equal(method,'POST');assert.deepEqual(Object.keys(body).sort(),['expected_published_revision','expected_revision','records']);assert.equal(body.expected_published_revision,state.finance.published.revision)
    const next=structuredClone(state.finance.published)
    for(const item of body.records){assert.deepEqual(Object.keys(item).sort(),['record_id','source_checksum','source_revision']);const meta=ledger.record_meta[item.record_id];assert.equal(meta.record_author_id,77);assert.equal(meta.draft_actor_id,77);assert.equal(item.source_revision,meta.draft_revision);assert.equal(item.source_checksum,meta.draft_checksum);const row=ledger.records.find(row=>row.project_id===meta.project_id);next.records=next.records.filter(row=>row.project_id!==meta.project_id);next.records.push(structuredClone(row));next.record_meta[item.record_id]=structuredClone(meta)}
    Object.assign(next,{revision:ledger.revision+1,id:crypto.randomUUID()});state.finance.published=next;ledger.state='published'
   }else if(suffix===''&&method==='PATCH'){assert.deepEqual(Object.keys(body).sort(),['as_of','expected_revision']);ledger.as_of=body.as_of;ledger.state='draft'}
   else{state.unexpected.push({path,method});return json({detail:'禁止财务提交/退回或其他写入'},501)}
   ledger.revision++;return json(ledger)
  }
  const lm=path.match(/^\/api\/business\/ledgers\/(presales|engineering)\/(.*)$/)
  if(lm){const department=lm[1],suffix=lm[2];let ledger=state.ledger[department]
   if(method==='GET')return json(ledger)
   const body=request.postDataJSON();state.writes.push({path,method,body})
   assert.equal(body.expected_revision,ledger.revision)
   if(state.conflict){state.conflict=false;ledger.revision++;if(department==='presales')ledger.records[0].notes='并发修改后的备注';else ledger.records[0].owner='并发修改后的负责人';return json({detail:'版本冲突'},409)}
   if(suffix.startsWith('records/')){
    assert.equal(ledger.permissions.can_edit,true);assert.notEqual(ledger.state,'submitted');assert.deepEqual(Object.keys(body).sort(),['expected_revision','record'])
    const fields=department==='presales'?presalesFields:engineeringFields;assert.ok(Object.keys(body.record).every(key=>key in fields))
    const id=suffix.slice(8).replace(/\/$/,'');assert.equal(method,id?'PUT':'POST')
    if(id){const at=ledger.records.findIndex(item=>item.project_id===decodeURIComponent(id));assert.ok(at>=0);ledger.records[at]=body.record}else ledger.records.push(body.record)
    ledger.state='draft';ledger.source_name='手工录入'
   }
   else if(suffix==='submit/'){assert.equal(method,'POST');assert.equal(ledger.permissions.can_submit,true);assert.equal(ledger.state,'draft');assert.deepEqual(Object.keys(body),['expected_revision']);ledger.state='submitted';ledger.last_return_reason=''}
   else if(suffix==='publish/'){assert.equal(method,'POST');assert.equal(ledger.permissions.can_publish,true);assert.equal(ledger.state,'submitted');assert.deepEqual(Object.keys(body),['expected_revision']);ledger.state='published'}
   else if(suffix==='return/'){assert.equal(method,'POST');assert.equal(ledger.permissions.can_publish,true);assert.equal(ledger.state,'submitted');assert.deepEqual(Object.keys(body).sort(),['expected_revision','reason']);assert.ok(body.reason.trim());ledger.state='draft';ledger.last_return_reason=body.reason}
   else if(suffix===''&&method==='PATCH'){assert.equal(ledger.permissions.can_edit,true);assert.notEqual(ledger.state,'submitted');assert.deepEqual(Object.keys(body).sort(),['as_of','expected_revision']);ledger.as_of=body.as_of;ledger.state='draft'}
   else {state.unexpected.push({path,method});return json({detail:'未配置隔离写入契约'},501)}
   ledger.revision++;return json(ledger)
  }
  if(method!=='GET'){state.unexpected.push({path,method});return json({detail:'验收禁止此请求'},501)}
  if(path==='/api/business/boards/finance/')return state.financeError?json({detail:'当前账号没有看板权限'},state.financeError):json(board(state.source,url.searchParams.get('q')||''))
  if(path==='/api/product/tasks/')return json({tasks:[options.task || task]})
  if(path===`/api/product/tasks/${task.id}/`)return json(options.task || task)
  if(path.endsWith('/history/'))return json({task_id:task.id,task_version:1,history_immutable:false,tamper_claim:'',timeline:[]})
  if(path===`/api/product/tasks/${task.id}/outputs/`)return json({task_version:1,outputs:options.outputs || [{id:'sdd-preview-output',family:'feasibility',version:1,sha256:'isolated-hash',current:true,stale:false,draft:true,approved:false,engine:'isolated',content_version:1,content_sha256:'content',content_approved:false,source_versions:[],has_preview:true,page_count:1}]})
  if(path==='/api/product/outputs/sdd-preview-output/preview/')return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="420"><rect width="300" height="420" fill="white"/><text x="30" y="60" font-size="20">Isolated preview</text></svg>'})
  if(path==='/api/product/outputs/sdd-preview-output/download/')return route.fulfill({contentType:'application/octet-stream',headers:{'Content-Disposition':'attachment; filename="isolated-report.docx"'},body:'isolated-download-bytes'})
  if(path.endsWith('/outputs/'))return json({outputs:[],pagination:{page:1,page_size:12,total:0,pages:0}})
  if(path==='/api/product/workspace/')return json({as_of:'2026-10-14',scope:'authorized_projects',metrics:{all:1,active:1,completed:0,review:0,generation:0,completed_month:0},projects:[task],pagination:{page:1,page_size:20,total:1,pages:1},recent_projects:[task],todos:[],recent_outputs:[],reviewers:[],capabilities:{model_generation:false,retrieval:false,formal_release:false,office_preview:true,upload_extensions:['.pdf','.xlsx'],upload_max_bytes:20000000},templates:[]})
  if(path==='/api/product/opportunities/')return json({items:[{id:1,project_name:'验收样例 · 公告商机',project_code:'T-001',region:'陕西',purchaser:'样例采购单位',budget:{amount_yuan:null,cap_yuan:null,raw:''},publish_at:null,publish_date:'2026-10-14',publish_precision:'date',bid_deadline:null,status:'ACTIVE',participation_status:'unknown',source:null,original_url:null,current_version:1,first_seen_at:null,notice_category:'procurement',user_state:{is_read:false,is_favorite:false,is_irrelevant:false}}],total:1,page:1,page_size:20,has_more:false,stats:{total:18,today_new:3,latest_batch_new:5,closing_soon:2},last_updated_at:'2026-10-14T01:00:00Z'})
  if(path==='/api/product/opportunities/1/')return json({id:1,project_name:'验收样例 · 公告商机',project_code:'T-001',region:'陕西',purchaser:'样例采购单位',budget:{amount_yuan:null,cap_yuan:null,raw:''},publish_precision:'date',publish_date:'2026-10-14',bid_deadline:null,status:'ACTIVE',source:null,current_version:1,notices:[],versions:[],attachments:[],contact:{},unknown_fields:[],field_evidence:{},user_state:{is_read:false,is_favorite:false,is_irrelevant:false}})
  if(path==='/api/product/options/')return json({regions:[{value:'陕西',label:'陕西'}],industries:[],notice_categories:[]})
  if(path==='/api/product/sources/')return json([])
  if(path==='/api/product/refresh/')return json({available:false,enabled:false,unavailable_reason:'隔离验收不执行采集'})
  if(path==='/api/engineering/jobs/')return json({jobs:options.engineeringJobs || [],capabilities:{cost:{status:'ready'},ragflow:{status:'not_configured'}}})
  if(path==='/api/engineering/knowledge/')return json({status:'not_configured',detail:'隔离验收只检查已有页面'})
  if(path==='/api/product/knowledge/status/')return json({available:true,code:'ready',help:''})
  if(path==='/api/product/knowledge/datasets/')return json({datasets:[]})
  if(path==='/api/product/knowledge/conversations/')return json({conversations:[]})
  if(path==='/api/hr/recruitment/requests/')return json([hrRequest])
  if(path===`/api/hr/recruitment/requests/${hrRequest.id}/`)return json(hrRequest)
  if(path===`/api/hr/recruitment/requests/${hrRequest.id}/jd-versions/`)return json([hrJd])
  if(path===`/api/hr/recruitment/requests/${hrRequest.id}/history/`)return json({request:hrRequest,messages:[{id:'message-check',role:'user',content:'岗位需求',created_at:'2026-10-14T01:00:00Z',input_version:1,jd_version_id:null}],jd_versions:[hrJd],batches:[{...hrBatch,results:[hrResult]}]})
  if(path==='/api/hr/recruitment/batches/')return json([hrBatch])
  if(path===`/api/hr/recruitment/batches/${hrBatch.id}/progress/`)return json(hrBatch)
  if(path===`/api/hr/recruitment/batches/${hrBatch.id}/summary/`)return json([hrResult])
  if(path===`/api/hr/recruitment/resumes/${hrResult.id}/`)return json({match:{matrix:hrResult.matrix}})
  state.unexpected.push({path,method});return json({detail:'未配置隔离验收接口'},501)
 })
 const page=await context.newPage();page.setDefaultTimeout(7000);page.on('pageerror',error=>state.pageErrors.push(error.message))
 return{context,page,state}
}
async function visit(page,path){await page.goto(base+path);await page.waitForLoadState('networkidle')}
async function screenshot(page,name){await page.screenshot({path:resolve(output,name),fullPage:false})}
async function traverse(page,direction,path){await page.waitForLoadState('networkidle');const count=await page.evaluate(()=>window.__sddEvents.length);await page.evaluate(value=>history[value](),direction);await page.waitForFunction(({count,path})=>window.__sddEvents.length>count&&location.pathname===path,{count,path})}
async function shellCheck(page,name,width,height){
 await page.locator('.enterprise-business').waitFor()
 const geometry=await page.evaluate(()=>{
  const aside=document.querySelector('.enterprise-shell > aside'),header=document.querySelector('.enterprise-shell > div > header'),main=document.querySelector('.enterprise-shell > div > main')
  const box=el=>{const r=el.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height}}
  return{aside:aside&&box(aside),header:header&&box(header),main:box(main),content:box(document.querySelector('.enterprise-business')),finance:document.querySelector('.finance-board')&&box(document.querySelector('.finance-board')),documentWidth:document.documentElement.scrollWidth,viewport:innerWidth,businessSurfaces:document.querySelectorAll('.enterprise-business').length,productShell:document.querySelector('.gm-product-shell')&&box(document.querySelector('.gm-product-shell')),productArea:document.querySelector('.gm-product-shell > .wb-work-area')&&box(document.querySelector('.gm-product-shell > .wb-work-area'))}
 })
 assert.equal(geometry.aside.width,224);assert.equal(geometry.aside.x,0);assert.equal(geometry.header.height,60)
 assert.equal(geometry.documentWidth,geometry.viewport);assert.equal(geometry.businessSurfaces,1)
 assert.equal(geometry.content.x,224+28);assert.equal(geometry.content.width,width-224-56)
 if(geometry.finance){assert.equal(geometry.finance.x,geometry.content.x);assert.equal(geometry.finance.width,geometry.content.width)}
 if(geometry.productShell)assert.equal(geometry.productShell.x,geometry.productArea.x)
 evidence.viewportChecks.push({name,width,height,...geometry})
}
const browser=await playwright.chromium.launch({headless:true})
try{
 if(!process.env.SDD_ENTRY_ONLY){
 const gm=await session()
 const routes=[['opportunities','/departments/product/opportunities'],['documents','/departments/product/documents?view=projects'],['estimate','/departments/engineering/estimate'],['knowledge','/departments/product/knowledge'],['finance','/departments/business/finance']]
 for(const [width,height] of [[1440,900],[1920,1080],[2450,1106]]){
  await gm.page.setViewportSize({width,height})
  for(const[name,path]of routes){await visit(gm.page,path);await shellCheck(gm.page,name,width,height);const links=await gm.page.locator('.gm-nav-link').allTextContents();assert.deepEqual(links,['商机看板','文档生成','产品报价','知识检索','财务看板']);await screenshot(gm.page,`${name}-${width}.png`)}
 }
 await visit(gm.page,'/departments/product/documents?view=projects');assert.equal(await gm.page.getByRole('heading',{name:'历史项目',exact:true}).count(),1)
 await gm.page.getByRole('link',{name:'新建项目',exact:true}).first().click();await gm.page.waitForURL('**view=new');await gm.page.locator('.wb-new-project').waitFor();assert.equal(await gm.page.locator('.wb-new-project').count(),1)
 await gm.page.goBack();await gm.page.waitForURL('**view=projects');await gm.page.goForward();await gm.page.waitForURL('**view=new')
 await gm.page.getByRole('link',{name:'成果文件',exact:true}).click();await gm.page.waitForURL('**/outputs');await gm.page.reload();await gm.page.waitForLoadState('networkidle');assert.equal(await gm.page.locator('.enterprise-business').count(),1)
 await visit(gm.page,`/departments/product/documents?task=${task.id}`);await gm.page.getByText('验收样例 · 数字化项目',{exact:true}).first().waitFor();await gm.page.getByRole('button',{name:'预览首页',exact:true}).click();await gm.page.getByAltText('可研报告当前版本首页预览').waitFor();await gm.page.waitForFunction(()=>Array.from(document.images).some(image=>image.alt.includes('当前版本首页预览')&&image.complete&&image.naturalWidth>0));await screenshot(gm.page,'document-detail-1920.png');const downloading=gm.page.waitForEvent('download');await gm.page.getByRole('button',{name:'下载文件',exact:true}).click();const download=await downloading;assert.equal(download.suggestedFilename(),'isolated-report.docx');assert.equal(readFileSync(await download.path(),'utf8'),'isolated-download-bytes')
 evidence.interactions.push('manager five entries; document defaults/history/new/outputs; browser back/forward; deep-link refresh; project detail; existing authenticated download bytes and preview')
 await visit(gm.page,'/departments/business/finance');await gm.page.getByLabel('搜索项目、业主、负责人或状态').fill('甲项目');await gm.page.getByRole('button',{name:'筛选',exact:true}).click();await gm.page.waitForURL('**q=*');await gm.page.waitForFunction(()=>document.querySelectorAll('.finance-table-scroll tbody tr').length===1);assert.equal(await gm.page.locator('.finance-table-scroll tbody tr').count(),1);assert.match(await gm.page.locator('.finance-metric').first().innerText(),/100/)
 gm.state.source=true;await gm.page.getByRole('button',{name:'刷新财务看板'}).click();await gm.page.getByText('原表金额单位未核实',{exact:false}).waitFor();assert.equal(await gm.page.locator('.finance-donut-layout').count(),0);assert.equal(await gm.page.locator('.finance-metric').count(),5);await screenshot(gm.page,'finance-source-1920.png')
 gm.state.financeError=403;await gm.page.getByRole('button',{name:'刷新财务看板'}).click();await gm.page.getByRole('alert').waitFor();assert.equal(await gm.page.locator('.finance-metrics').count(),0);await screenshot(gm.page,'finance-403.png')
 gm.state.financeError=401;await gm.page.getByRole('button',{name:'刷新财务看板'}).click();await gm.page.getByText('重新登录或绑定',{exact:false}).waitFor();evidence.interactions.push('finance same-range server filtering; source mode five metrics and no money chart; 403/401 clear old content')
 assert.deepEqual(gm.state.unexpected,[]);assert.deepEqual(gm.state.pageErrors,[]);assert.deepEqual(gm.state.writes,[]);await gm.context.close()
 const saved=(id,family,chapterId,text)=>({id,family,version:1,input_hash:'input-current',blueprint_hash:'blueprint-current',payload:{chapter_id:chapterId,title:'共同标题',paragraphs:[text],source_ids:['1']}})
 const reportTask={...structuredClone(task),state:'FAILED',stage:'WRITING',blueprint_version:2,blueprint_approved:true,blueprint:{id:'report-blueprint',version:2,sha256:'blueprint-current',input_hash:'input-current',payload:{purpose:'隔离验收',audience:'评审',chapters:[{id:'t1',family:'technical-solution',title:'共同标题',scope:'技术',source_ids:['1']},{id:'f1',family:'feasibility',title:'共同标题',scope:'可研',source_ids:['1']}],conditions:[],missing:[],conflicts:[]}},chapters:[saved('valid-t','technical-solution','t1','有效技术正文'),saved('valid-f','feasibility','f1','有效可研正文'),saved('wrong-t','technical-solution','f1','串入技术报告的可研稿'),saved('wrong-f','feasibility','t1','串入可研报告的技术稿')],actions:['retry'],retry_budget:{used:1,limit:3,remaining:2}}
 const reportOutput=(family,extra={})=>({id:`isolated-${family}`,family,version:1,sha256:'isolated-report-hash',current:true,stale:false,draft:true,approved:false,engine:'isolated',content_version:1,content_sha256:'content',content_approved:false,source_versions:[],...extra})
 const quality={issue_count:1,issues:[{code:'quantity_mismatch',text:'设备数量需对照项目底稿核对'}],figures:{planned:15,rendered:13,pending_count:2,pending:[{figure_id:'figure-14',error_code:'diagram_render_failed'},{figure_id:'figure-15',error_code:'diagram_render_failed'}]},actual_characters:40000,minimum_characters:50000}
 for(const scenario of ['family','quality-running','quality-failed','no-file','delivery']){
  const currentTask=structuredClone(reportTask)
  let outputs=[]
  if(scenario.startsWith('quality')){currentTask.state=scenario==='quality-running'?'RUNNING':'FAILED';currentTask.analysis_progress={writing_technical:{status:'completed'},diagrams_technical:{status:'pending'}};outputs=[reportOutput('technical-solution',{quality_warnings:quality})]}
  if(scenario==='no-file'){currentTask.error_code='diagram_render_failed';currentTask.retry_budget={used:3,limit:3,remaining:0};currentTask.quality_warnings=[{family:'technical-solution',issue_count:1,issues:[{code:'quantity_mismatch'}]}]}
  if(scenario==='delivery'){currentTask.state='WAITING_INPUT';currentTask.error_code='delivery_incomplete';outputs=['technical-solution','feasibility','presentation'].map(family=>reportOutput(family,family==='presentation'?{delivery_decision:{status:'draft',delivered:false,blocking_issues:[{code:'presentation_quality_failed'},{code:'diagram_pending'}]}}:{draft:false,delivered:true,review_status:'delivered'}))}
  const probe=await session(manager,{task:currentTask,outputs});diagnosticPage=probe.page
  await probe.page.setViewportSize({width:1920,height:1080})
  await visit(probe.page,`/departments/product/documents?task=${task.id}&tab=${scenario==='delivery'?'presentation':'technical-solution'}`)
  const workspace=probe.page.locator('.pd-artifact-workspace');await workspace.waitFor()
  if(scenario==='family'){
   for(const[family,valid,other]of [['technical-solution','有效技术正文','有效可研正文'],['feasibility','有效可研正文','有效技术正文']]){
    if(family==='feasibility')await probe.page.getByRole('tab',{name:'可研报告',exact:true}).click()
    const body=probe.page.locator('.wb-saved-content');assert.equal(await body.getByText(valid,{exact:true}).count(),0);assert.equal(await body.locator('details').count(),1)
    await body.locator('summary').click();await body.getByText(valid,{exact:true}).waitFor();assert.doesNotMatch(await body.innerText(),new RegExp(`${other}|串入技术报告的可研稿|串入可研报告的技术稿`))
    await screenshot(probe.page,`report-family-${family}.png`)
   }
  }else if(scenario==='delivery'){
   await probe.page.getByRole('button',{name:'继续生成',exact:true}).waitFor();await probe.page.getByRole('button',{name:'查看问题',exact:true}).waitFor()
   assert.equal(await probe.page.getByRole('button',{name:'下载文件',exact:true}).count(),4)
   const details=workspace.locator('section[aria-label="汇报 PPT交付问题"]');await details.getByText('查看全部 2 项交付问题',{exact:true}).click()
   await details.getByText('PPT 质量检查尚未通过',{exact:true}).waitFor();await details.getByText('图表仍需补生成',{exact:true}).waitFor();await screenshot(probe.page,'report-delivery-expanded.png')
  }else{
   const warnings=workspace.locator('[aria-label="成果质量提示"]');await warnings.getByText('查看待核对问题',{exact:true}).click()
   await warnings.getByText(scenario==='no-file'?'设备数量与项目底稿不一致，需核对原始清单':'设备数量需对照项目底稿核对',{exact:true}).waitFor()
   if(scenario==='no-file'){assert.equal(await probe.page.getByRole('button',{name:'从已保存进度重试',exact:true}).isEnabled(),false);assert.equal(await probe.page.getByRole('button',{name:'下载文件',exact:true}).count(),0);await probe.page.getByText('正文已保存，文件待生成',{exact:true}).first().waitFor()}
   else{assert.match(await warnings.innerText(),/图表待补：已渲染 13 \/ 15 张，待补 2 张/);assert.match(await warnings.innerText(),/低于当前最低 50,000 字/);assert.ok(await probe.page.getByRole('button',{name:'下载文件',exact:true}).count()>0)}
   await screenshot(probe.page,`report-${scenario}-expanded.png`)
  }
  assert.deepEqual(probe.state.writes,[]);assert.deepEqual(probe.state.unexpected,[]);assert.deepEqual(probe.state.pageErrors,[]);evidence.reportChecks.push({scenario,status:'PASS',writes:probe.state.writes.length});await probe.context.close()
 }
 evidence.interactions.push('report disclosure: correct-family body and no cross-family text; issue text/code descriptions on expansion; quality counts and saved downloads; exhausted retry disabled; delivery reasons with four saved download buttons; no report writes')
 }
 for(const department of ['product','engineering']){
  const employee=await session({...manager,id:`isolated-${department}`,username:'验收员工',business_role:'employee',department_code:department,capabilities:[department]})
  const {page,state}=employee;diagnosticPage=page;const code=department==='product'?'presales':'engineering'
  for(const[width,height]of [[1440,900],[1920,1080]]){await page.setViewportSize({width,height});await visit(page,`/departments/${department}/entry`);await page.getByRole('heading',{name:department==='product'?'售前填报':'工程填报',exact:true}).waitFor();assert.equal(await page.locator('.enterprise-business').count(),1);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await screenshot(page,`${code}-entry-${width}.png`)}
  await page.getByRole('link',{name:department==='product'?'账号与设置':'设置',exact:true}).click();await page.waitForURL('**/settings');await page.getByRole('link',{name:department==='product'?'售前填报':'工程填报',exact:true}).click();await page.waitForURL(`**/departments/${department}/entry`);await page.getByRole('button',{name:'编辑',exact:true}).first().click();await page.locator('#entry-project_name').fill('本次编辑内容');await screenshot(page,`${code}-editor-1920.png`)
  state.conflict=true;await page.getByRole('button',{name:'保存草稿',exact:true}).click();await page.getByRole('heading',{name:'请核对版本变化'}).waitFor();assert.equal(await page.locator('#entry-project_name').inputValue(),'本次编辑内容');assert.equal(state.writes.length,1);await screenshot(page,`${code}-conflict.png`)
  await page.getByRole('button',{name:'已核对，继续本次修改'}).click();await page.getByRole('button',{name:'保存草稿',exact:true}).click();await page.getByText('草稿已保存，尚未提交或发布。').waitFor();assert.equal(state.writes.at(-1).body.expected_revision,8)
  if(code==='presales'){assert.equal(state.writes.at(-1).body.record.follow_up_history,record.follow_up_history);assert.equal(state.writes.at(-1).body.record.notes,'并发修改后的备注');assert.equal(state.writes.at(-1).body.record.amount,'')}
  else assert.equal(state.writes.at(-1).body.record.owner,'并发修改后的负责人')
  const metadataRevision=state.ledger[code].revision
  await page.locator('#ledger-cutoff').fill('2026-10-13');await page.getByRole('button',{name:'保存日期',exact:true}).click();await page.getByText('台账截止日期已保存。',{exact:true}).waitFor()
  assert.deepEqual(state.writes.at(-1),{path:`/api/business/ledgers/${code}/`,method:'PATCH',body:{expected_revision:metadataRevision,as_of:'2026-10-13'}})
  assert.equal(state.ledger[code].revision,metadataRevision+1);assert.equal(await page.getByRole('button',{name:'提交台账',exact:true}).isEnabled(),true);assert.equal(await page.getByRole('button',{name:'发布台账',exact:true}).isEnabled(),false)
  await screenshot(page,`${code}-metadata.png`)
  const submitRevision=state.ledger[code].revision
  await page.getByRole('button',{name:'提交台账',exact:true}).click();await page.getByText('台账已提交，等待授权发布。').waitFor();assert.equal(await page.getByRole('button',{name:'新增项目',exact:true}).isEnabled(),false)
  assert.deepEqual(state.writes.at(-1),{path:`/api/business/ledgers/${code}/submit/`,method:'POST',body:{expected_revision:submitRevision}})
  assert.equal(await page.getByRole('button',{name:'提交台账',exact:true}).isEnabled(),false);assert.equal(await page.getByRole('button',{name:'发布台账',exact:true}).isEnabled(),true);assert.equal(await page.getByRole('button',{name:'保存日期',exact:true}).isEnabled(),false)
  assert.equal(await page.getByRole('button',{name:'退回修改',exact:true}).isEnabled(),false)
  await page.locator('#ledger-return-reason').fill('请核对项目进度依据。');assert.equal(await page.getByRole('button',{name:'发布台账',exact:true}).isEnabled(),false)
  const returnRevision=state.ledger[code].revision
  await page.getByRole('button',{name:'退回修改',exact:true}).click();await page.getByText('台账已退回，可继续编辑。',{exact:true}).waitFor()
  assert.deepEqual(state.writes.at(-1),{path:`/api/business/ledgers/${code}/return/`,method:'POST',body:{expected_revision:returnRevision,reason:'请核对项目进度依据。'}})
  assert.equal(state.ledger[code].state,'draft');assert.equal(state.ledger[code].last_return_reason,'请核对项目进度依据。');assert.equal(await page.getByRole('button',{name:'新增项目',exact:true}).isEnabled(),true);assert.equal(await page.getByRole('button',{name:'发布台账',exact:true}).isEnabled(),false)
  await screenshot(page,`${code}-returned-draft.png`)
  const resubmitRevision=state.ledger[code].revision
  await page.getByRole('button',{name:'提交台账',exact:true}).click();await page.getByText('台账已提交，等待授权发布。').waitFor();assert.equal(state.writes.at(-1).body.expected_revision,resubmitRevision)
  const publishRevision=state.ledger[code].revision
  await page.getByRole('button',{name:'发布台账',exact:true}).click();await page.getByText('台账已发布。',{exact:true}).waitFor();assert.equal(state.ledger[code].state,'published');assert.deepEqual(state.writes.at(-1),{path:`/api/business/ledgers/${code}/publish/`,method:'POST',body:{expected_revision:publishRevision}})
  const workflowWrites=structuredClone(state.writes.slice(2))
  state.ledger[code].state='draft';state.ledger[code].revision++;state.ledger[code].permissions={can_edit:false,can_submit:true,can_publish:false}
  await page.getByRole('button',{name:'刷新数据',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.ledger-status').textContent==='草稿');assert.equal(await page.getByRole('button',{name:'新增项目',exact:true}).isEnabled(),false);assert.equal(await page.getByRole('button',{name:'提交台账',exact:true}).isEnabled(),true);assert.equal(await page.getByRole('button',{name:'发布台账',exact:true}).isEnabled(),false)
  await page.getByRole('button',{name:'查看',exact:true}).first().click();assert.equal(await page.locator('#entry-project_name').evaluate(input=>input.readOnly),true);assert.equal(await page.getByRole('button',{name:'保存草稿',exact:true}).isEnabled(),false);await page.getByRole('button',{name:'返回列表',exact:true}).click()
  state.ledger[code].state='submitted';state.ledger[code].revision++;state.ledger[code].permissions={can_edit:true,can_submit:true,can_publish:false}
  await page.getByRole('button',{name:'刷新数据',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.ledger-status').textContent.includes('已提交'));assert.equal(await page.getByRole('button',{name:'新增项目',exact:true}).isEnabled(),false);assert.equal(await page.getByRole('button',{name:'提交台账',exact:true}).isEnabled(),false);assert.equal(await page.getByRole('button',{name:'发布台账',exact:true}).isEnabled(),false);assert.equal(await page.locator('#ledger-return-reason').count(),0)
  state.ledger[code].revision++;state.ledger[code].permissions={can_edit:false,can_submit:false,can_publish:true}
  await page.getByRole('button',{name:'刷新数据',exact:true}).click();await page.getByRole('button',{name:'发布台账',exact:true}).waitFor();await page.waitForFunction(()=>!Array.from(document.querySelectorAll('button')).find(button=>button.textContent==='发布台账').disabled);assert.equal(await page.getByRole('button',{name:'新增项目',exact:true}).isEnabled(),false);assert.equal(await page.locator('#ledger-return-reason').count(),1)
  await screenshot(page,`${code}-publisher-permissions.png`)
  state.ledger[code].state='published';state.ledger[code].revision++;state.ledger[code].permissions={can_edit:true,can_submit:true,can_publish:true}
  await page.getByRole('button',{name:'刷新数据',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.ledger-status').textContent==='已发布')
  await page.getByRole('button',{name:'新增项目',exact:true}).click();await page.locator('#entry-project_name').fill('标准新增验收项目')
  const beforeInvalid=state.writes.length, invalidCases=[]
  if(code==='presales'){
   assert.equal(await page.locator('#entry-status').inputValue(),'');assert.equal(await page.locator('#entry-amount').inputValue(),'')
   await page.getByRole('button',{name:'保存草稿',exact:true}).click();assert.equal(await page.locator('#entry-status').evaluate(input=>input.validity.valueMissing),true);assert.equal(await page.locator('#entry-amount').evaluate(input=>input.validity.valueMissing),true);assert.equal(state.writes.length,beforeInvalid);invalidCases.push('missing status and amount: no POST')
   await page.locator('#entry-status').selectOption('线索');await page.getByRole('button',{name:'保存草稿',exact:true}).click();assert.equal(await page.locator('#entry-amount').evaluate(input=>input.validity.valueMissing),true);assert.equal(state.writes.length,beforeInvalid);invalidCases.push('missing amount: no POST')
   await page.locator('#entry-amount').fill('0');await page.locator('#entry-status').selectOption('');await page.getByRole('button',{name:'保存草稿',exact:true}).click();assert.equal(await page.locator('#entry-status').evaluate(input=>input.validity.valueMissing),true);assert.equal(state.writes.length,beforeInvalid);invalidCases.push('missing status with explicit zero amount: no POST')
   await page.locator('#entry-status').selectOption('线索')
  }else{
   await page.locator('#entry-status').selectOption('待开工');assert.equal(await page.locator('#entry-progress').inputValue(),'');await page.getByRole('button',{name:'保存草稿',exact:true}).click();assert.equal(await page.locator('#entry-progress').evaluate(input=>input.validity.valueMissing),true);assert.equal(state.writes.length,beforeInvalid);invalidCases.push('unknown progress: no POST')
   await page.locator('#entry-progress').fill('0')
  }
  await screenshot(page,`${code}-new-required-validation.png`)
  const createRevision=state.ledger[code].revision
  await page.getByRole('button',{name:'保存草稿',exact:true}).click();await page.getByText('草稿已保存，尚未提交或发布。').waitFor();assert.equal(state.writes.length,beforeInvalid+1)
  const created=state.writes.at(-1);assert.equal(created.method,'POST');assert.equal(created.path,`/api/business/ledgers/${code}/records/`);assert.equal(created.body.expected_revision,createRevision);assert.match(created.body.record.project_id,code==='presales'?/^PS-/:/^EG-/);assert.equal(created.body.record[code==='presales'?'amount':'progress'],'0');assert.equal('source_sheet' in created.body.record,false)
  evidence.ledgerChecks.push({department:code,workflowWrites,invalidCases,created,permissionCases:['draft submitter without edit/publish','submitted editor without publish','submitted publisher without edit/submit']})
  // Clean SPA navigation creates a real forward target before opening the dirty form.
  await page.getByRole('link',{name:department==='product'?'账号与设置':'设置',exact:true}).click();await page.waitForURL('**/settings');await traverse(page,'back',`/departments/${department}/entry`);await page.getByRole('button',{name:'新增项目',exact:true}).waitFor()
  await page.getByRole('button',{name:'新增项目',exact:true}).click();assert.equal(await page.locator(code==='presales'?'#entry-amount':'#entry-progress').inputValue(),'');await page.locator('#entry-project_name').fill('未保存验收输入')
  let prompts=0;const dismiss=async dialog=>{prompts++;evidence.lastDialog=dialog.message();await dialog.dismiss()};page.on('dialog',dismiss)
  await page.getByRole('link',{name:department==='product'?'账号与设置':'设置',exact:true}).click();assert.equal(new URL(page.url()).pathname,`/departments/${department}/entry`)
  evidence.guardBefore=await page.evaluate(()=>({href:location.href,state:history.state}));await traverse(page,'back',`/departments/${department}/entry`);evidence.guardAfter=await page.evaluate(()=>({href:location.href,state:history.state,events:window.__sddEvents}));assert.equal(await page.locator('#entry-project_name').inputValue(),'未保存验收输入');assert.ok(prompts>=2)
  const beforeForwardPrompts=prompts,writesBeforeLeave=state.writes.length
  await traverse(page,'forward',`/departments/${department}/entry`);assert.equal(prompts,beforeForwardPrompts+1);assert.equal(await page.locator('#entry-project_name').inputValue(),'未保存验收输入');assert.equal(state.writes.length,writesBeforeLeave);await screenshot(page,`${code}-dirty-forward-cancelled.png`)
  const cancelledHistory=await page.evaluate(()=>({href:location.href,state:history.state,events:window.__sddEvents}));let acceptedPrompts=0
  page.off('dialog',dismiss);const accept=async dialog=>{acceptedPrompts++;await dialog.accept()};page.on('dialog',accept)
  await traverse(page,'forward','/settings');await page.waitForURL('**/settings');assert.equal(acceptedPrompts,1);assert.equal(await page.locator('#entry-project_name').count(),0);assert.equal(state.writes.length,writesBeforeLeave);await screenshot(page,`${code}-dirty-forward-confirmed.png`)
  page.off('dialog',accept);await traverse(page,'back',`/departments/${department}/entry`);await page.getByRole('button',{name:'新增项目',exact:true}).waitFor();assert.equal(await page.locator('#entry-project_name').count(),0)
  evidence.navigationChecks.push({department:code,cancelledPrompts:prompts,acceptedPrompts,cancelledHistory,confirmedForwardPath:'/settings',writesBeforeLeave,writesAfterLeave:state.writes.length,returnHasUnsavedEditor:false})
  evidence.interactions.push(`${code}: source preservation and 409 reconciliation; exact metadata/submit/return/publish revisions; state and permission matrices; standard required fields block POST; explicit zero create; dirty click/back/forward cancellation and confirmed forward leave`)
  assert.deepEqual(state.unexpected,[]);assert.deepEqual(state.pageErrors,[]);await employee.context.close()
 }
 for(const source of [false,true]){
  const employee=await session(financeEmployee,{financeSource:source});diagnosticPage=employee.page
  const {page,state}=employee
  await visit(page,'/departments/finance');await page.getByRole('link',{name:'财务填报',exact:true}).last().click();await page.locator('.finance-records').waitFor()
  for(const [width,height] of [[1440,900],[1920,1080]]){await page.setViewportSize({width,height});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await screenshot(page,`finance-entry-${source?'source':'standard'}-${width}.png`)}
  assert.equal(await page.getByRole('button',{name:'提交',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'退回',exact:true}).count(),0)
  assert.equal(await page.getByLabel('选择发布 他人财务项目').isDisabled(),true);assert.equal(await page.getByLabel('选择发布 归属未知财务项目').isDisabled(),true)
  const other=page.locator('.finance-records tbody tr').filter({hasText:'他人财务项目'});await other.getByRole('button',{name:'查看',exact:true}).click();assert.equal(await page.getByLabel('项目名称',{exact:false}).isEditable(),false);assert.equal(await page.getByRole('button',{name:'保存草稿',exact:true}).isDisabled(),true);await page.getByRole('button',{name:'返回列表',exact:true}).click()
  await page.locator('.finance-records tbody tr').filter({hasText:'本人财务项目'}).getByRole('button',{name:'编辑',exact:true}).click()
  if(source){await page.getByText('月度回款（来源年度未核实）',{exact:true}).click();assert.equal(await page.getByLabel('1月实际回款').inputValue(),'10');assert.equal(await page.getByLabel('2月实际回款').inputValue(),'');await page.locator('.finance-months').scrollIntoViewIfNeeded();await screenshot(page,'finance-entry-source-months.png');await page.getByLabel('1月实际回款').fill('0')}
  else{assert.equal(await page.getByLabel('已收金额（元）',{exact:false}).inputValue(),'20');assert.equal(await page.getByLabel('应收日期',{exact:false}).inputValue(),'')}
  await page.getByText('主体及其他信息',{exact:true}).click();await page.getByLabel('业主单位',{exact:false}).fill('本人修改业主')
  state.conflict=true;await page.getByRole('button',{name:'保存草稿',exact:true}).click();await page.getByRole('heading',{name:'版本冲突，请人工核对'}).waitFor();assert.equal(await page.getByLabel('业主单位',{exact:false}).inputValue(),'本人修改业主');assert.equal(state.writes.length,1);await screenshot(page,`finance-entry-conflict-${source?'source':'standard'}.png`)
  await page.getByRole('button',{name:'已核对，继续本次修改',exact:true}).click();await page.getByRole('button',{name:'保存草稿',exact:true}).click();await page.getByText('本人草稿已保存，尚未发布。',{exact:true}).waitFor();assert.equal(state.writes.length,2);assert.equal(state.finance.ledger.records[0].billing_entity,'并发更新主体');if(source){assert.equal(state.finance.ledger.records[0].received_01,'0');assert.equal(state.finance.ledger.records[0].received_02,'');assert.equal(state.finance.ledger.records[0].source_row,'8')}
  const otherPublished=structuredClone(state.finance.published.records.find(row=>row.project_id==='FN-other'))
  await page.getByLabel('选择发布 本人财务项目').check();page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'确认发布本人记录',exact:true}).click();await page.getByText('选定本人记录已发布。',{exact:true}).waitFor();assert.equal(state.writes.length,3);assert.equal(state.writes[2].body.records.length,1);assert.equal(state.writes[2].body.expected_published_revision,3);assert.equal(state.writes[2].body.records[0].record_id,financeId);assert.equal(state.writes[2].body.records[0].source_revision,9);assert.deepEqual(state.finance.published.records.find(row=>row.project_id==='FN-other'),otherPublished);assert.equal(state.finance.published.records.find(row=>row.project_id==='FN-own').client_name,'本人修改业主');assert.equal(await page.getByLabel('选择发布 本人财务项目').isDisabled(),true)
  await page.getByRole('button',{name:'新增记录',exact:true}).click();await page.getByLabel('项目名称',{exact:false}).fill('新增本人财务项目');await page.getByLabel('合同金额',{exact:false}).fill('0')
  if(source){await page.getByLabel('已收金额',{exact:false}).fill('0');await page.getByRole('button',{name:'保存草稿',exact:true}).click();await page.getByRole('alert').filter({hasText:'不能在本台账主动混入标准记录'}).waitFor();assert.equal(state.writes.length,3);await page.getByLabel('年初应收',{exact:false}).fill('0')}
  else{await page.getByRole('button',{name:'保存草稿',exact:true}).click();assert.equal(state.writes.length,3);await page.getByLabel('已收金额',{exact:false}).fill('0')}
  await page.getByRole('button',{name:'保存草稿',exact:true}).click();await page.getByText('本人草稿已保存，尚未发布。',{exact:true}).waitFor();assert.equal(state.writes.length,4);const created=state.writes[3].body.record;assert.equal(created.contract_amount,'0');assert.equal(created.source_sheet,undefined);assert.equal(created.source_row,undefined);assert.equal(source?created.opening_receivable:created.received_amount,'0')
  await page.locator('.finance-records tbody tr').filter({hasText:'新增本人财务项目'}).getByRole('button',{name:'编辑',exact:true}).click();await page.getByLabel('项目名称',{exact:false}).fill('未保存财务修改');page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('link',{name:'设置',exact:true}).click();assert.ok(page.url().includes('/departments/finance/entry'));assert.equal(await page.getByLabel('项目名称',{exact:false}).inputValue(),'未保存财务修改');assert.equal(state.writes.length,4)
  page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'返回列表',exact:true}).click();assert.equal(await page.getByLabel('项目名称',{exact:false}).inputValue(),'未保存财务修改');page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'返回列表',exact:true}).click()
  state.financeError=403;await page.getByRole('button',{name:'刷新数据',exact:true}).click();await page.getByRole('alert').waitFor();assert.equal(await page.locator('.finance-records,.ledger-editor').count(),0);await screenshot(page,'finance-entry-403.png');state.financeError=401;await page.getByRole('button',{name:'重新读取',exact:true}).click();await page.getByText('重新登录或检查业务绑定',{exact:false}).waitFor();assert.equal(await page.locator('.finance-records,.ledger-editor').count(),0);assert.deepEqual(state.unexpected,[]);assert.deepEqual(state.pageErrors,[])
  evidence.ledgerChecks.push({department:'finance',mode:source?'source':'standard',writes:state.writes,checks:['two desktop sizes','own/other/unknown author','standard required received','source 12 months blank vs real zero','original fields merge after 409','exact own publish ignores generic can_publish','others published unchanged','new record no fake source','no mixing modes','dirty leave cancelled','403 clears data']});await employee.context.close()
 }
 const financeDenied=await session(financeEmployee,{grant:false});await visit(financeDenied.page,'/departments/finance');assert.equal(await financeDenied.page.getByRole('link',{name:'财务填报',exact:true}).count(),0);await visit(financeDenied.page,'/departments/finance/entry');await financeDenied.page.getByRole('alert').waitFor();assert.equal(await financeDenied.page.locator('.finance-records,.ledger-editor').count(),0);assert.equal(financeDenied.state.writes.length,0);await financeDenied.context.close()
 const denied=await session({...manager,business_role:'employee',department_code:'engineering',capabilities:['engineering']},{grant:false})
 await visit(denied.page,'/departments/engineering');assert.equal(await denied.page.getByRole('link',{name:'工程填报',exact:true}).count(),0)
 await visit(denied.page,'/departments/engineering/entry');await denied.page.getByText('未获该台账访问权限',{exact:false}).waitFor();assert.equal(await denied.page.locator('.ledger-editor,.ledger-table').count(),0)
 await visit(denied.page,'/departments/business/finance');await denied.page.getByRole('heading',{name:'没有访问权限'}).waitFor();assert.equal(await denied.page.locator('.finance-board').count(),0);assert.deepEqual(denied.state.unexpected,[]);await denied.context.close()
 const limited=await session({...manager,capabilities:['engineering']},{reduced:true});await visit(limited.page,'/departments/engineering/estimate');assert.deepEqual(await limited.page.locator('.gm-nav-link').allTextContents(),['产品报价']);assert.equal(await limited.page.evaluate(()=>document.querySelector('main').getAnimations().length),0);await limited.context.close()
 evidence.interactions.push('department no-grant entry hidden/deep-link denied; employee finance guard; partial manager capabilities; reduced motion')
 const productRoutes=['/departments/product','/departments/product/documents','/departments/product/documents?view=projects',`/departments/product/documents?task=${task.id}`,'/departments/product/opportunities','/departments/product/knowledge','/departments/product/outputs']
 const hrRoutes=['/departments/hr','/departments/hr/jobs',`/departments/hr/jobs?task=${hrRequest.id}`,'/departments/hr/resumes',`/departments/hr/resumes?results=1&batch=${hrBatch.id}`,'/departments/hr/history',`/departments/hr/history?task=${hrRequest.id}`]
 const engineeringRoutes=['/departments/engineering','/departments/engineering/estimate','/departments/engineering/jobs']
 evidence.pageLayoutChecks=[]
 for(const role of ['manager','product','hr','engineering','finance']){
  const user=role==='manager'?manager:{...manager,id:`layout-${role}`,username:'页面验收员工',business_role:'employee',department_code:role,capabilities:[role]}
  const current=await session(user);diagnosticPage=current.page
  const paths=role==='manager'?[...productRoutes,...hrRoutes,...engineeringRoutes,'/departments/business/finance']:role==='product'?[...productRoutes,'/departments/product/entry']:role==='hr'?hrRoutes:role==='engineering'?[...engineeringRoutes,'/departments/engineering/entry']:['/departments/finance','/departments/finance/entry']
  for(const [width,height] of [[1280,800],[1440,900],[1920,1080],[2450,1106]]){
   await current.page.setViewportSize({width,height})
   for(const path of paths){
    await visit(current.page,path)
    const layout=await current.page.evaluate(()=>{
     const main=document.querySelector('main'),nav=document.querySelector('.wb-navigation')||document.querySelector('.enterprise-shell > aside'),root=main.firstElementChild
     const box=el=>{const r=el.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,right:r.right}}
     const content=document.querySelector('.wb-work-content'),panel=content?.firstElementChild
     const style=getComputedStyle(content||main),available=(content||main).clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight)
     return{documentWidth:document.documentElement.scrollWidth,mainWidth:main.clientWidth,mainScrollWidth:main.scrollWidth,root:box(root),sidebar:box(nav),panel:panel&&box(panel),available,animations:main.getAnimations().length,viewport:innerWidth,rootAvailable:main.clientWidth-parseFloat(getComputedStyle(main).paddingLeft)-parseFloat(getComputedStyle(main).paddingRight)}
    })
    assert.equal(layout.documentWidth,width,`${role} ${path}: document overflow`)
    assert.ok(layout.mainScrollWidth<=layout.mainWidth+1,`${role} ${path}: main overflow ${JSON.stringify(layout)}`)
    assert.equal(layout.sidebar.width,224,`${role} ${path}: sidebar width`)
    assert.ok(Math.abs(layout.root.width-layout.rootAvailable)<1,`${role} ${path}: constrained page root`)
    if(layout.panel)assert.ok(Math.abs(layout.panel.width-layout.available)<1,`${role} ${path}: constrained product panel ${JSON.stringify(layout)}`)
    assert.equal(layout.animations,0,`${role} ${path}: page fade`)
    evidence.pageLayoutChecks.push({role,path,width,...layout})
    if(width===1920)await screenshot(current.page,`layout-${role}-${paths.indexOf(path)}.png`)
   }
  }
  assert.deepEqual(current.state.unexpected,[]);assert.deepEqual(current.state.pageErrors,[]);assert.deepEqual(current.state.writes,[])
  await current.context.close()
 }
 const longJob={id:'layout-long-job',status:'completed',files:[{name:'LongEquipmentList'.repeat(20)+'.xlsx'}],result:{download_available:false}}
 const stress=await session({...manager,business_role:'employee',department_code:'engineering',capabilities:['engineering']},{engineeringJobs:[longJob]});diagnosticPage=stress.page
 evidence.longNameChecks=[]
 for(const width of [1280,1440,1920,2450]){
  await stress.page.setViewportSize({width,height:900});await visit(stress.page,'/departments/engineering/jobs')
  await stress.page.locator('.engineering-task-name').waitFor()
  const geometry=await stress.page.evaluate(()=>{const main=document.querySelector('main'),name=document.querySelector('.engineering-task-name'),row=name.closest('li'),box=el=>{const r=el.getBoundingClientRect();return{left:r.left,right:r.right}};return{documentWidth:document.documentElement.scrollWidth,mainWidth:main.clientWidth,mainScrollWidth:main.scrollWidth,name:box(name),row:box(row)}})
  assert.equal(geometry.documentWidth,width);assert.ok(geometry.mainScrollWidth<=geometry.mainWidth+1);assert.ok(geometry.name.right<=geometry.row.right+1)
  evidence.longNameChecks.push({width,...geometry})
 }
 assert.deepEqual(stress.state.unexpected,[]);assert.deepEqual(stress.state.pageErrors,[]);assert.deepEqual(stress.state.writes,[]);await stress.context.close()
 evidence.status='PASS'
}catch(error){if(diagnosticPage&&!diagnosticPage.isClosed())await screenshot(diagnosticPage,'acceptance-failure.png');evidence.status='FAIL';evidence.failures.push(error.stack);throw error}finally{writeFileSync(resolve(output,'browser-results.json'),JSON.stringify(evidence,null,2));await browser.close()}
console.log(`Desktop browser acceptance ${evidence.status}: ${evidence.pageLayoutChecks.length} page layout checks; ${evidence.longNameChecks.length} long-name checks; ${evidence.viewportChecks.length} manager viewport checks; ${evidence.interactions.length} interaction groups. Evidence: ${output}`)
