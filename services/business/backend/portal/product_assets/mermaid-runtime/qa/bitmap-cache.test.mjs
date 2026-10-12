import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { bitmapBinding, confined, loadBitmap, saveBitmap, sha256 } from "../bitmap-cache.mjs";

const png=Buffer.from([137,80,78,71,13,10,26,10,1,2,3]);
const figure={id:"D1",caption:"synthetic title"};
const diagram={source:'flowchart LR\nA["evidence"] --> B["synthetic"]',anchor_text:"evidence"};
const runtime={bundleSha256:"a".repeat(64),manifestSha256:"b".repeat(64),rendererSha256:"c".repeat(64)};

test("bitmap checkpoint binds source, title, anchor and runtime without persisting text",async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),"bitmap-cache-"));
  try {
    const destination=await confined(root,"diagram.png");
    await fs.writeFile(destination,png);
    const binding=bitmapBinding(figure,diagram,runtime);
    await saveBitmap(root,binding,destination);
    await fs.unlink(destination);
    assert.equal(await loadBitmap(root,binding,destination),sha256(png));
    for (const altered of [bitmapBinding({...figure,caption:"changed"},diagram,runtime),
      bitmapBinding(figure,{...diagram,source:diagram.source+"\nB --> C"},runtime),
      bitmapBinding(figure,{...diagram,anchor_text:"changed"},runtime),
      bitmapBinding(figure,diagram,{...runtime,rendererSha256:"d".repeat(64)}),
      bitmapBinding(figure,diagram,{...runtime,bundleSha256:"d".repeat(64)})]) {
      assert.equal(await loadBitmap(root,altered,destination),null);
    }
    const metadata=await fs.readFile(path.join(root,".bitmap-cache",sha256(JSON.stringify(binding))+".json"),"utf8");
    assert.ok(!metadata.includes("synthetic title") && !metadata.includes("flowchart") && !metadata.includes("evidence"));
    await fs.writeFile(path.join(root,".bitmap-cache",sha256(JSON.stringify(binding))+".png"),"tampered");
    assert.equal(await loadBitmap(root,binding,destination),null);
  } finally { await fs.rm(root,{recursive:true,force:true}); }
});

test("bitmap paths refuse traversal and linked cache destinations",async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),"bitmap-path-"));
  const outside=await fs.mkdtemp(path.join(os.tmpdir(),"bitmap-outside-"));
  try {
    for (const relative of ["../outside.png",outside,"x/../outside.png"]) {
      await assert.rejects(()=>confined(root,relative));
    }
    await fs.symlink(outside,path.join(root,"linked"),process.platform==="win32"?"junction":"dir");
    await assert.rejects(()=>confined(root,"linked/image.png"));
    assert.deepEqual(await fs.readdir(outside),[]);
  } finally { await fs.rm(root,{recursive:true,force:true}); await fs.rm(outside,{recursive:true,force:true}); }
});

test("a later Mermaid parse failure retains earlier bitmap and retry reuses it",{skip:!process.env.PORTAL_CHROMIUM_PATH},async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),"bitmap-retry-"));
  const renderer=fileURLToPath(new URL("../render.mjs",import.meta.url));
  const content=path.join(root,"content.json"),input=path.join(root,"private.json");
  const run=(sources)=>{
    return fs.writeFile(input,JSON.stringify({diagrams:sources})).then(()=>spawnSync(process.execPath,[renderer,content,input],{encoding:"utf8",timeout:60000}));
  };
  try {
    await fs.writeFile(content,JSON.stringify({blocks:[{...figure,type:"figure",path:"one.png"},{id:"D2",caption:"second",type:"figure",path:"two.png"}]}));
    const broken={figure_id:"D2",source:"flowchart LR\nA[",anchor_text:""};
    const first=await run([{figure_id:"D1",...diagram},broken]);
    assert.equal(first.status,2);
    assert.equal(JSON.parse(first.stderr).reason,"diagram_parse_or_anchor_failed");
    await assert.rejects(()=>fs.stat(input),{code:"ENOENT"});
    const checkpoint=path.join(root,".bitmap-cache",(await fs.readdir(path.join(root,".bitmap-cache"))).find((name)=>name.endsWith(".png")));
    const initial=await fs.stat(checkpoint);
    const second=await run([{figure_id:"D1",...diagram},{figure_id:"D2",source:'flowchart LR\nA["second"] --> B["ready"]',anchor_text:"second"}]);
    assert.equal(second.status,0,second.stderr);
    assert.equal(JSON.parse(second.stdout).rendered,2);
    assert.equal((await fs.stat(checkpoint)).mtimeMs,initial.mtimeMs);
    assert.equal((await fs.readdir(path.join(root,".bitmap-cache"))).filter((name)=>name.endsWith(".png")).length,2);
  } finally { await fs.rm(root,{recursive:true,force:true}); }
});
