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
    const source='flowchart TB\nA["光纤测温系统"] --> B["采集温度数据"]\nB --> C["核对采样状态"]\nC --> D{"温度阈值待确认"}\nD -->|条件待确认| E["记录告警信息"]\nD -->|正常| F["持续监控"]\nE --> G["通知值班人员"]\nG --> H["人工复核告警"]';
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
    assert.equal(first.layoutVersion,"word-readable-v3");
    assert.equal(long.layout.panels.length,1);assert.equal(long.layout.labelsFullyContained,true);
    assert.equal(long.layout.nodeCount,8);assert.ok(long.layout.labelCount>=10);assert.ok(long.layout.edgeCount>=7);
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
    const extra=long.layout.panels[0];await fs.writeFile(path.join(root,extra.path),"corrupt published panel");
    const third=await render();assert.deepEqual(third.figures,first.figures);
    assert.equal(createHash("sha256").update(await fs.readFile(path.join(root,extra.path))).digest("hex"),extra.imageSha256);
    const layoutFiles=(await fs.readdir(path.join(root,".bitmap-cache"))).filter(name=>name.endsWith(".layout.json"));
    for(const name of layoutFiles){
      const location=path.join(root,".bitmap-cache",name),cached=JSON.parse(await fs.readFile(location,"utf8"));
      cached.version="word-readable-v1";cached.panels.push(cached.panels[0],cached.panels[0]);
      cached.obsoleteLayoutSentinel=true;
      await fs.writeFile(location,JSON.stringify(cached));
    }
    const afterOldCache=await render();
    // A real screenshot can differ in raster bytes across browser processes.
    // Re-rendered geometry/source must agree and each new bitmap must verify.
    const withoutBitmapHashes=value=>JSON.parse(JSON.stringify(value,(key,item)=>key==="imageSha256" ? undefined : item));
    assert.deepEqual(withoutBitmapHashes(afterOldCache.figures),withoutBitmapHashes(first.figures));
    for(const [index,figure]of afterOldCache.figures.entries()){
      assert.equal(figure.sourceSha256,createHash("sha256").update(diagrams[index].source).digest("hex"));
      assert.equal(figure.layout.version,"word-readable-v3");assert.ok(figure.layout.panels.length<=2);
      assert.equal(figure.imageSha256,figure.layout.panels[0].imageSha256);
      for(const panel of figure.layout.panels){
        const actual=await fs.readFile(path.join(root,panel.path));
        assert.equal(createHash("sha256").update(actual).digest("hex"),panel.imageSha256);
      }
    }
    for(const name of layoutFiles){
      const refreshed=JSON.parse(await fs.readFile(path.join(root,".bitmap-cache",name),"utf8"));
      assert.equal(refreshed.version,"word-readable-v3");assert.ok(refreshed.panels.length<=2);
      assert.equal(refreshed.obsoleteLayoutSentinel,undefined);
    }
    const tooLong=path.join(root,"too-long");await fs.mkdir(tooLong);
    await fs.writeFile(path.join(tooLong,"content.json"),JSON.stringify({blocks:[{...figures[0],path:"long.png"}]}));
    const longer=source+'\nH --> I["处置结果待确认"]\nI --> J["记录处置结果"]\nJ --> K["恢复监控"]\nK --> L["告警闭环待确认"]'+Array.from({length:8},(_,index)=>`\n${String.fromCharCode(76+index)} --> ${String.fromCharCode(77+index)}["附加核查待确认"]`).join("");
    await fs.writeFile(path.join(tooLong,"private.json"),JSON.stringify({diagrams:[{figure_id:"D1",source:longer,anchor_text:"光纤测温系统"}]}));
    const fragmented=spawnSync(process.execPath,[path.join(runtime,"render.mjs"),path.join(tooLong,"content.json"),path.join(tooLong,"private.json")],{env:process.env,encoding:"utf8",windowsHide:true,timeout:60000});
    assert.equal(fragmented.status,2);const fragmentedLayout=JSON.parse(fragmented.stderr);
    assert.equal(fragmentedLayout.reason,"diagram_layout_unreadable");assert.equal(fragmentedLayout.detail,"too_many_reading_units");
    assert.ok(fragmentedLayout.readingUnitCount>2);assert.equal(fragmentedLayout.maximumReadingUnits,2);
    assert.ok(fragmentedLayout.directionCandidates.length>=1);assert.ok(fragmentedLayout.minFontPt>=10.5);
    assert.equal(await fs.stat(path.join(tooLong,"long.png")).then(()=>true,()=>false),false);
    const unreadable=path.join(root,"unreadable");await fs.mkdir(unreadable);
    await fs.writeFile(path.join(unreadable,"content.json"),JSON.stringify({blocks:[{...figures[0],path:"wide.png"}]}));
    const wide='flowchart TB\nA["入口待确认"]\n'+Array.from({length:6},(_,i)=>`A --> B${i}["同阶段核验条件待确认${i}"]`).join("\n");
    await fs.writeFile(path.join(unreadable,"private.json"),JSON.stringify({diagrams:[{figure_id:"D1",source:wide,anchor_text:"入口待确认"}]}));
    const rescued=spawnSync(process.execPath,[path.join(runtime,"render.mjs"),path.join(unreadable,"content.json"),path.join(unreadable,"private.json")],{env:process.env,encoding:"utf8",windowsHide:true,timeout:60000});
    assert.equal(rescued.status,0,rescued.stderr);
    const rescuedLayout=JSON.parse(rescued.stdout).figures[0].layout;
    assert.equal(rescuedLayout.sourceDirection,"TB");assert.equal(rescuedLayout.direction,"LR");
    assert.ok(rescuedLayout.minFontPt>=10.5);assert.equal(rescuedLayout.nodeCount,7);
    const tooNarrow=path.join(root,"too-narrow");await fs.mkdir(tooNarrow);
    await fs.writeFile(path.join(tooNarrow,"content.json"),JSON.stringify({blocks:[{...figures[0],path:"wide.png",width_mm:20}]}));
    await fs.writeFile(path.join(tooNarrow,"private.json"),JSON.stringify({diagrams:[{figure_id:"D1",source:wide,anchor_text:"入口待确认"}]}));
    const rejected=spawnSync(process.execPath,[path.join(runtime,"render.mjs"),path.join(tooNarrow,"content.json"),path.join(tooNarrow,"private.json")],{env:process.env,encoding:"utf8",windowsHide:true,timeout:60000});
    assert.equal(rejected.status,2);const failedLayout=JSON.parse(rejected.stderr);
    assert.equal(failedLayout.reason,"diagram_layout_unreadable");assert.equal(failedLayout.detail,"font_below_minimum");
    assert.equal(failedLayout.figure_id,"D1");assert.equal(failedLayout.directionCandidates.length,3);
    assert.ok(failedLayout.directionCandidates.every(item=>item.minFontPt<10.5&&item.nodeCount===7&&item.edgeCount===6));
    assert.equal(await fs.stat(path.join(tooNarrow,"wide.png")).then(()=>true,()=>false),false);
    assert.equal(await fs.stat(path.join(tooNarrow,"private.json")).then(()=>true,()=>false),false);
  } finally {await fs.rm(root,{recursive:true,force:true});}
});
