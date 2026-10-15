import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {spawnSync} from "node:child_process";
import {fileURLToPath} from "node:url";
import test from "node:test";

const runtime=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
test("actual SVG rows reject split digits and allow unit and English wraps",{skip:!process.env.PORTAL_CHROMIUM_PATH},async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),"mermaid-numeric-wrap-"));
  try{
    async function render(name,label){
      const directory=path.join(root,name);await fs.mkdir(directory);
      await fs.writeFile(path.join(directory,"content.json"),JSON.stringify({blocks:[{id:"D1",type:"figure",path:"figure.png",width_mm:145}]}));
      await fs.writeFile(path.join(directory,"private.json"),JSON.stringify({diagrams:[{figure_id:"D1",source:`flowchart TB\nA["${label}"] --> B["人工复核待确认"]`,anchor_text:"315kVA"}]}));
      const result=spawnSync(process.execPath,[path.join(runtime,"render.mjs"),path.join(directory,"content.json"),path.join(directory,"private.json")],{env:process.env,encoding:"utf8",windowsHide:true,timeout:60000});
      assert.equal(await fs.stat(path.join(directory,"private.json")).then(()=>true,()=>false),false);
      return {result,directory};
    }
    const bad=await render("split-digits","核对400kVA/2000kVA/315kVA实际负载分配");
    assert.equal(bad.result.status,2,bad.result.stderr);
    const failure=JSON.parse(bad.result.stderr);
    assert.equal(failure.reason,"diagram_layout_unreadable");
    assert.equal(failure.detail,"numeric_token_split");assert.equal(failure.figure_id,"D1");
    assert.ok(failure.numericSplitCount>=1);assert.ok(failure.minFontPt>=10.5);
    assert.ok(failure.directionCandidates.length>=1);
    assert.ok(failure.directionCandidates.every(item=>Number.isFinite(item.minFontPt)&&item.nodeCount===2&&item.edgeCount===1));
    assert.equal(bad.result.stderr.includes("315kVA"),false);
    assert.equal(await fs.stat(path.join(bad.directory,"figure.png")).then(()=>true,()=>false),false);
    for(const [name,label] of [["separate-values","400kVA 2000kVA 315kVA"],["unit-english","315kVA Controller communication verification pending"]]){
      const good=await render(name,label);assert.equal(good.result.status,0,good.result.stderr);
      const evidence=JSON.parse(good.result.stdout);assert.equal(evidence.figures[0].layout.nodeCount,2);
      assert.ok(evidence.figures[0].layout.minFontPt>=10.5);
      assert.equal(evidence.blockedNetworkRequests,0);assert.equal(evidence.securityLevel,"strict");
      assert.ok((await fs.stat(path.join(good.directory,"figure.png"))).size>2000);
    }
  }finally{await fs.rm(root,{recursive:true,force:true});}
});
