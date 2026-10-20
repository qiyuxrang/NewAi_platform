import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as jsx from 'react/jsx-runtime'
import { availableManagerEntries, canAccessFinanceBoard, canAccessEntry } from '../src/enterprise-navigation.ts'
import { businessPath, apiRequest, businessFileUrl, downloadBusinessFile, businessFilePreview } from '../src/business/api.ts'
const manager = { business_role: 'general_manager', capabilities: ['general_manager', 'product', 'engineering'] }
test('manager entries keep order/defaults and finance/entry guards do not expand access', () => {
 assert.deepEqual(availableManagerEntries(manager).map(item => item.label), ['商机看板', '文档生成', '产品报价', '智能助手', '财务看板', '企业资质库'])
 assert.equal(availableManagerEntries(manager)[1].to, '/departments/product/documents?view=projects')
 assert.deepEqual(availableManagerEntries({...manager, capabilities:['engineering']}).map(item=>item.label), ['产品报价'])
 assert.equal(canAccessFinanceBoard({...manager,capabilities:[]}),false)
 assert.equal(canAccessFinanceBoard({business_role:'employee',capabilities:['general_manager']}),false)
 assert.equal(canAccessEntry(manager,'product'),false)
 assert.equal(canAccessEntry({business_role:'employee',department_code:'product',capabilities:['product']},'product'),true)
 assert.equal(canAccessEntry({business_role:'employee',department_code:'engineering',capabilities:['product','engineering']},'product'),false)
 assert.equal(canAccessEntry({business_role:'employee',department_code:'finance',capabilities:['finance']},'finance'),true)
 assert.equal(canAccessEntry({...manager,capabilities:['general_manager','finance']},'finance'),false)
 assert.equal(canAccessFinanceBoard({business_role:'employee',department_code:'finance',capabilities:['finance']}),false)
})
test('business root is additive; request, upload, auth, preview and download semantics are retained', async () => {
 for (const root of ['product','hr','engineering','business']) assert.equal(businessPath(`/api/${root}/items/`), `/api/enterprise/business/${root}/items/`)
 assert.throws(()=>businessPath('/api/business/../admin/'))
 assert.throws(()=>businessPath('/api/admin/users/'))
 const previous = {fetch:globalThis.fetch,localStorage:globalThis.localStorage,document:globalThis.document}
 const calls=[]; let downloaded=''
 globalThis.localStorage={getItem:()=> 'isolated-test-token'}
 globalThis.fetch=async(url,options)=>{calls.push({url,options});return url.includes('download')? new Response('isolated bytes',{headers:{'Content-Disposition':"attachment; filename*=UTF-8''report.docx"}}): url.includes('preview')? new Response('<p>isolated preview</p>',{headers:{'Content-Type':'text/html'}}): Response.json({ok:true})}
 globalThis.document={createElement:()=>({click(){},set download(value){downloaded=value}})}
 try {
  const controller=new AbortController()
  await apiRequest('/api/business/boards/finance/',{signal:controller.signal})
  const form=new FormData();form.set('expected_version','7')
  await apiRequest('/api/product/sources/',{method:'POST',body:form})
  assert.equal(calls.at(-1).options.body,form);assert.equal(calls.at(-1).options.headers.has('Content-Type'),false)
  await downloadBusinessFile('/api/product/artifacts/a/download/','fallback.docx');assert.equal(downloaded,'report.docx')
  const preview=await businessFilePreview('/api/product/artifacts/a/preview/',controller.signal);assert.equal(preview.content,'<p>isolated preview</p>')
  const url=await businessFileUrl('/api/product/artifacts/a/download/',controller.signal);URL.revokeObjectURL(url)
  for(const call of calls){assert.equal(call.options.headers.get('Authorization'),'Bearer isolated-test-token');assert.equal(call.options.credentials,'omit')}
 } finally {Object.assign(globalThis,previous)}
})
test('manager keeps fixed shared shell on every route; employee product workbench remains intact', () => {
 const compiled=ts.transpileModule(readFileSync(new URL('../src/components/Layout.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText
 function render(pathname,business_role,reduced=false){const exports={};const effects=[];let animations=0;const component=()=>null
  vm.runInNewContext(compiled,{exports,require:name=>name==='react/jsx-runtime'?jsx:name==='react'?{useEffect:effect=>effects.push(effect),useRef:()=>({current:{animate:()=>{animations++;return {cancel(){}}}}})}:name==='react-router-dom'?{Outlet:component,useLocation:()=>({pathname,search:''})}:{default:component,NotificationProvider:component,useEnterprise:()=>({user:{business_role}})},window:{matchMedia:()=>({matches:reduced})}})
  const shell=exports.default().props.children;effects.forEach(effect=>effect());return{shell,animations}
 }
 for(const path of availableManagerEntries(manager).map(item=>item.to.split('?')[0])){const result=render(path,'general_manager');assert.match(result.shell.props.className,/manager-workspace/);assert.doesNotMatch(result.shell.props.className,/workbuddy-product/);assert.ok(result.shell.props.children[0]);assert.ok(result.shell.props.children[1].props.children[0]);assert.equal(result.animations,0)}
 assert.match(render('/departments/product/knowledge','employee').shell.props.className,/workbuddy-product/)
 assert.match(render('/departments/product/entry','employee').shell.props.className,/workbuddy-product/)
 assert.equal(render('/departments/business/finance','general_manager',true).animations,0)
})
