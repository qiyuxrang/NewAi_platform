import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {spawnSync} from "node:child_process";
import {createHash} from "node:crypto";
import {fileURLToPath} from "node:url";
import test from "node:test";

const runtime=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
test("actual cropped reading units preserve source and reuse every panel",{skip:!process.env.PORTAL_CHROMIUM_PATH},async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),"mermaid-readable-"));
  try {
    const source='flowchart TB\nA["光纤测温系统"] --> B["采集温度数据"]\nB --> C["核对采样状态"]\nC --> D{"温度阈值待确认"}\nD -->|条件待确认| E["记录告警信息"]\nD -->|正常| F["持续监控"]\nE --> G["通知值班人员"]\nG --> H["人工复核告警"]\nH --> I["处置结果待确认"]\nI --> J["记录处置结果"]\nJ --> K["恢复监控"]\nK --> L["告警闭环待确认"]';
    const figures=[{id:"D1",type:"figure",path:"long.png",caption:"光纤测温系统待确认",width_mm:145},
      {id:"D2",type:"figure",path:"wide.png",caption:"横流程待确认",width_mm:145},
      {id:"D3",type:"figure",path:"sequence.png",caption:"时序待确认",width_mm:145}];
    const diagrams=[{figure_id:"D1",source,anchor_text:"光纤测温系统"},
      {figure_id:"D2",source:'flowchart LR\nA["资料接收"] --> B["资料核对待确认"]\nB --> C["现场复核待确认"]\nC --> D["形成结果待确认"]',anchor_text:"资料接收"},
      {figure_id:"D3",source:'sequenceDiagram\nparticipant A as 采集端\nparticipant B as 复核端\nA->>B:温度告警待确认\nB-->>A:复核结果待确认',anchor_text:"温度告警待确认"}];
    await fs.writeFile(path.join(root,"content.json"),JSON.stringify({blocks:figures}));
    async function render(){
      await fs.writeFile(path.join(root,"private.json"),JSON.stringify({diagrams}));
      const result=spawnSync(process.execPath,[path.join(runtime,"render.mjs"),path.join(root,"content.json"),path.join(root,"private.json")],{env:process.env,encoding:"utf8",windowsHide:true,timeout:120000});
      assert.equal(result.status,0,result.stderr);assert.equal(await fs.stat(path.join(root,"private.json")).then(()=>true,()=>false),false);
      return JSON.parse(result.stdout);
    }
    const first=await render();
    assert.equal(first.blockedNetworkRequests,0);assert.equal(first.securityLevel,"strict");
    const long=first.figures[0];assert.equal(long.sourceSha256,createHash("sha256").update(source).digest("hex"));
    assert.ok(long.layout.panels.length>1);assert.equal(long.layout.labelsFullyContained,true);
    assert.equal(long.layout.nodeCount,12);assert.ok(long.layout.labelCount>=14);assert.ok(long.layout.edgeCount>=11);
    const times=new Map();
    for(const figure of first.figures){
      for(const panel of figure.layout.panels){
        assert.ok(panel.min_font_pt>=10.5);assert.ok(panel.width_mm<=145);assert.ok(panel.css_width<1000);
        const bytes=await fs.readFile(path.join(root,panel.path));
        assert.equal(bytes.readUInt32BE(16),Math.round(panel.css_width*1.5));
        assert.ok(bytes.readUInt32BE(20)<1400);assert.ok(bytes.length>2000);
      }
    }
    for(const name of await fs.readdir(path.join(root,".bitmap-cache")))if(name.endsWith(".png"))times.set(name,(await fs.stat(path.join(root,".bitmap-cache",name))).mtimeMs);
    const second=await render();assert.deepEqual(second.figures,first.figures);
    for(const [name,time]of times)assert.equal((await fs.stat(path.join(root,".bitmap-cache",name))).mtimeMs,time);
    const extra=long.layout.panels[1];await fs.writeFile(path.join(root,extra.path),"corrupt published panel");
    const third=await render();assert.deepEqual(third.figures,first.figures);
    assert.equal(createHash("sha256").update(await fs.readFile(path.join(root,extra.path))).digest("hex"),extra.imageSha256);
    const unreadable=path.join(root,"unreadable");await fs.mkdir(unreadable);
    await fs.writeFile(path.join(unreadable,"content.json"),JSON.stringify({blocks:[{...figures[0],path:"wide.png"}]}));
    const wide='flowchart TB\nA["入口待确认"]\n'+Array.from({length:6},(_,i)=>`A --> B${i}["同阶段核验条件待确认${i}"]`).join("\n");
    await fs.writeFile(path.join(unreadable,"private.json"),JSON.stringify({diagrams:[{figure_id:"D1",source:wide,anchor_text:"入口待确认"}]}));
    const rejected=spawnSync(process.execPath,[path.join(runtime,"render.mjs"),path.join(unreadable,"content.json"),path.join(unreadable,"private.json")],{env:process.env,encoding:"utf8",windowsHide:true,timeout:60000});
    assert.equal(rejected.status,2);assert.equal(JSON.parse(rejected.stderr).reason,"diagram_layout_unreadable");
    assert.equal(await fs.stat(path.join(unreadable,"wide.png")).then(()=>true,()=>false),false);
    assert.equal(await fs.stat(path.join(unreadable,"private.json")).then(()=>true,()=>false),false);
  } finally {await fs.rm(root,{recursive:true,force:true});}
});
