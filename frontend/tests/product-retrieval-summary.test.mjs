import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

test('retrieval dropdown separates recorded sources, bounds excerpts and handles missing history', () => {
  const text = readFileSync(new URL('../src/business/product/ProjectStages.tsx', import.meta.url), 'utf8');
  const source = ts.createSourceFile('ProjectStages.tsx', text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const node = source.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === 'RetrievalSummary');
  const compiled = ts.transpileModule(node.getText(source), {compilerOptions:{target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
  const Component = vm.runInNewContext(`${compiled}; RetrievalSummary`, {React});
  const task = { input: {knowledge_sources:[
    ...Array.from({length:5},(_,index)=>({id:`k${index}`,provider:'ragflow',title:`知识标题${index}`,text:'摘'.repeat(300)})),
    {id:'w1',provider:'tavily',fact_scope:'PUBLIC_REFERENCE',title:'公开标题',text:'<script>不可执行</script>'},
    {id:'unknown',title:'未分类来源',text:'不应混入检索结果'},
  ]}};
  const original = structuredClone(task);
  const render = kind => renderToStaticMarkup(React.createElement(Component,{task,kind}));
  const knowledge = render('knowledge');
  assert.match(knowledge, /查看检索内容（5 项）/);
  assert.equal((knowledge.match(/<li>/g)||[]).length,3);
  assert.match(knowledge, /仅展示前 3 项/);
  assert(!knowledge.includes('摘'.repeat(121)));
  assert.doesNotMatch(knowledge, /公开标题|未分类来源|<details[^>]*\sopen/);
  const web = render('web-search');
  assert.match(web, /公开标题/);
  assert.match(web, /&lt;script&gt;/);
  assert.match(web, /不作为项目事实/);
  assert.doesNotMatch(web, /知识标题|<script>/);
  assert.deepEqual(task,original);
  assert.match(renderToStaticMarkup(React.createElement(Component,{task:{},kind:'knowledge'})),/未保存可展示的检索内容/);
});
