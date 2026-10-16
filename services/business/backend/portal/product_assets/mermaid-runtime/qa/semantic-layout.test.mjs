import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {spawnSync} from "node:child_process";
import {createHash} from "node:crypto";
import {fileURLToPath} from "node:url";
import test from "node:test";

const runtime=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
test("semantic report layouts stay complete at readable Word size",{skip:!process.env.PORTAL_CHROMIUM_PATH},async()=>{
  const root=process.env.PORTAL_DIAGRAM_QA_OUTPUT || await fs.mkdtemp(path.join(os.tmpdir(),"mermaid-semantic-"));
  await fs.mkdir(root,{recursive:true});
  try {
    const fixtures=[
      ["service-flow","分级应急响应流程待确认","供配电设备清册",'flowchart TB\nA["供配电设备清册"] --> B["资料缺口分析"]\nB --> C["实施阶段采集"]\nC --> D["形成三级关联台账"]\nD --> E["制定分级应急预案"]\nE --> F{"判断服务类型"}\nF -->|非关键保护| G["低优先级响应"]\nF -->|关键保护| H["高优先级响应"]'],
      ["layered","分层架构待确认","业务入口",'flowchart TB\nsubgraph L1["接入层"]\nA["业务入口"]\nend\nsubgraph L2["处理层"]\nB["规则复核"]\nC["结果编制"]\nend\nsubgraph L3["资料层"]\nD["原始资料"]\nend\nA --> B\nB --> C\nB --> D'],
      ["zoned","部署边界待确认","现场采集",'flowchart TB\nsubgraph Z1["现场区待确认"]\nA["现场采集"]\nend\nsubgraph Z2["处理区待确认"]\nB["数据核对"]\nC["审计记录"]\nend\nA -->|采集数据| B\nB --> C'],
      ["decision","资料复核条件待确认","资料接收",'flowchart LR\nA["资料接收"] --> D{"完整待确认"}\nD -->|完整| B["人工复核"]\nD -->|缺失| C["补齐资料"]\nC --> A\nB --> E["交付待确认"]'],
      ["sequence","交互条件待确认","提交资料",'sequenceDiagram\nparticipant A as 提交端\nparticipant B as 复核端\nparticipant C as 归档端\nA->>B:提交资料\nalt 资料完整\nB->>C:保存结果\nC-->>B:返回记录\nB-->>A:完成待确认\nelse 资料缺失\nB-->>A:补齐资料\nend'],
    ];
    const blocks=fixtures.map(([name,caption])=>({id:name,type:"figure",path:`${name}.png`,caption,width_mm:145}));
    const diagrams=fixtures.map(([figure_id,,anchor_text,source])=>({figure_id,source,anchor_text}));
    const content=path.join(root,"content.json"),privatePath=path.join(root,"private.json");
    await fs.writeFile(content,JSON.stringify({blocks}));await fs.writeFile(privatePath,JSON.stringify({diagrams}));
    const rendered=spawnSync(process.execPath,[path.join(runtime,"render.mjs"),content,privatePath],{env:process.env,encoding:"utf8",windowsHide:true,timeout:120000});
    assert.equal(rendered.status,0,rendered.stderr);
    const evidence=JSON.parse(rendered.stdout);
    await fs.writeFile(path.join(root,"evidence.json"),JSON.stringify(evidence,null,2));
    assert.equal(evidence.rendered,5);assert.equal(evidence.blockedNetworkRequests,0);assert.equal(evidence.securityLevel,"strict");
    for(const [index,figure] of evidence.figures.entries()){
      assert.equal(figure.sourceSha256,createHash("sha256").update(diagrams[index].source).digest("hex"));
      assert.equal(figure.layout.panels.length,1,`${figure.figure_id} fragmented`);
      assert.ok(figure.layout.minFontPt>=10.5);assert.equal(figure.layout.labelsFullyContained,true);
      for(const panel of figure.layout.panels){
        assert.ok(panel.width_mm<=145);assert.ok(panel.css_height*panel.width_mm/panel.css_width<=190);
        assert.equal(createHash("sha256").update(await fs.readFile(path.join(root,panel.path))).digest("hex"),panel.imageSha256);
      }
    }
    assert.equal(await fs.stat(privatePath).then(()=>true,()=>false),false);
  } finally {if(!process.env.PORTAL_DIAGRAM_QA_OUTPUT)await fs.rm(root,{recursive:true,force:true});}
});
