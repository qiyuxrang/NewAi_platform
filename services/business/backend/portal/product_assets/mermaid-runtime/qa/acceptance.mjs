import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { chromium } from "playwright-core";
import { readVerifiedBundle, sha256 } from "../bundle-contract.mjs";
import { controlledContext } from "../browser-policy.mjs";

const runtime = path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const repository = path.resolve(runtime,"../../../..");
if (process.argv.length!==4 || process.argv[2]!=="--chromium") throw new Error("usage: acceptance.mjs --chromium trusted-chromium-executable");
const executable = path.resolve(process.argv[3]);
const round = path.join(repository,".runtime/mermaid-acceptance",randomUUID().replaceAll("-",""));
await fs.mkdir(round,{recursive:true});
const report = {schemaVersion:1,outcome:"RUNNING",round,syntheticOnly:true,productionDockerVerified:false};

async function sources() {
  const result={};
  const names=["package.json","pnpm-lock.yaml","pnpm-workspace.yaml","browser-entry.mjs","browser-policy.mjs","bundle-contract.mjs","build.mjs","render.mjs","qa/acceptance.mjs","qa/bundle-contract.test.mjs"];
  for(const name of names)result[name]=sha256(await fs.readFile(path.join(runtime,name)));
  result.Dockerfile=sha256(await fs.readFile(path.join(repository,"Dockerfile")));
  return result;
}

function child(argv,env) {
  return new Promise((resolve,reject)=>{
    const process=spawn(argv[0],argv.slice(1),{cwd:runtime,env,windowsHide:true,stdio:["ignore","pipe","pipe"]});
    let stdout="",stderr="";
    process.stdout.on("data",(chunk)=>{stdout+=chunk;});
    process.stderr.on("data",(chunk)=>{stderr+=chunk;});
    const timer=setTimeout(()=>{process.kill();},180000);
    process.on("error",(error)=>{clearTimeout(timer);reject(error);});
    process.on("close",(code)=>{clearTimeout(timer);resolve({code,stdout,stderr});});
  });
}

let browser;
try {
  report.sourceBefore=await sources();
  const {manifest,manifestSha256,bundle}=await readVerifiedBundle(path.join(runtime,"dist"));
  report.bundleSha256=manifest.bundleSha256;
  report.manifestSha256=manifestSha256;
  report.buildVersions=manifest.versions;
  report.compiledDependencyModules={};
  for(const name of ["katex","lodash-es"])report.compiledDependencyModules[name]=manifest.modules.filter((item)=>item.package===name).length;
  const fixture={blocks:Array.from({length:20},(_,index)=>({id:`F${index+1}`,type:"figure",path:`images/diagram-${index+1}.png`,
    caption:index===0?'合成标题 <img src="https://blocked.invalid/" onerror="window.probe=1">':`合成恢复图 ${index+1}`}))};
  const fixturePath=path.join(round,"content.json");
  await fs.writeFile(fixturePath,JSON.stringify(fixture));
  const privateInput=path.join(round,"private-input.json");
  const projectSources=fixture.blocks.map((figure,index)=>({figure_id:figure.id,
    anchor_text:`合成园区设备${index+1}`,
    source:`flowchart LR\nA["合成园区设备${index+1}"] --> B["设备${index+1}资料核对"]\nB --> C["设备${index+1}验收待确认"]`}));
  await fs.writeFile(privateInput,JSON.stringify({diagrams:projectSources}));
  const env={};
  for(const [key,value]of Object.entries(process.env))if(/^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|USERPROFILE|LOCALAPPDATA|APPDATA)$/i.test(key))env[key]=value;
  env.PORTAL_CHROMIUM_PATH=executable;
  const rendered=await child([process.execPath,path.join(runtime,"render.mjs"),fixturePath,privateInput],env);
  await fs.writeFile(path.join(round,"renderer.log"),rendered.stdout+"\n"+rendered.stderr);
  assert.equal(rendered.code,0,"actual renderer failed; see renderer.log");
  report.renderer=JSON.parse(rendered.stdout);
  assert.equal(report.renderer.rendered,20);
  assert.equal(report.renderer.bundleSha256,manifest.bundleSha256);
  assert.equal(report.renderer.manifestSha256,manifestSha256);
  assert.equal(report.renderer.blockedNetworkRequests,0);
  assert.equal(report.renderer.securityLevel,"strict");
  assert.equal(report.renderer.sourcePersisted,false);
  assert.equal(await fs.stat(privateInput).then(()=>true,()=>false),false,"private Mermaid source was retained");
  report.images=[];
  for(const figure of fixture.blocks){
    const bytes=await fs.readFile(path.join(round,figure.path));
    assert.equal(bytes.subarray(0,8).toString("hex"),"89504e470d0a1a0a");
    assert.equal(bytes.readUInt32BE(16),2400);
    assert.equal(bytes.readUInt32BE(20),1350);
    assert.ok(bytes.length>10000,"blank/invalid diagram output");
    report.images.push({path:figure.path,sha256:sha256(bytes),bytes:bytes.length,width:2400,height:1350});
  }
  assert.equal((await fs.readdir(path.join(round,"images"))).length,20);
  report.failureProbes=[];
  for (const [name,diagrams] of [["missing",projectSources.slice(1)],
    ["syntax",projectSources.map((item,index)=>index===0?{...item,source:'flowchart LR\nA["unterminated'}:item)],
    ["directive",projectSources.map((item,index)=>index===0?{...item,source:'%%{init: {"securityLevel":"loose"}}}%%\nflowchart LR\nA --> B'}:item)],
    ["invisible-evidence",projectSources.map((item,index)=>index===0?{...item,anchor_text:"报告依据未显示"}:item)]]) {
    const rejected=path.join(round,`rejected-${name}`);await fs.mkdir(rejected);
    const contentPath=path.join(rejected,"content.json"),sourcePath=path.join(rejected,"private.json");
    await fs.writeFile(contentPath,JSON.stringify(fixture));await fs.writeFile(sourcePath,JSON.stringify({diagrams}));
    const failed=await child([process.execPath,path.join(runtime,"render.mjs"),contentPath,sourcePath],env);
    assert.notEqual(failed.code,0,`${name} must fail without fallback`);
    assert.equal(await fs.stat(sourcePath).then(()=>true,()=>false),false);
    const images=await fs.readdir(path.join(rejected,"images")).catch(()=>[]);
    assert.equal(images.length,0,`${name} produced a fallback image`);
    report.failureProbes.push({name,blocked:true,sourceRetained:false,fallbackImages:images.length});
  }
  const frozenRoot=path.join(runtime,"../bj_docs");
  const frozenManifestBytes=await fs.readFile(path.join(frozenRoot,"manifest.json"));
  const frozenManifest=JSON.parse(frozenManifestBytes);
  for (const entry of frozenManifest.files) assert.equal(sha256(await fs.readFile(path.join(frozenRoot,entry.path))),entry.sha256);
  report.frozenManifestSha256=sha256(frozenManifestBytes);report.frozenVerifiedFiles=frozenManifest.files.length;
  browser=await chromium.launch({headless:true,executablePath:executable,args:["--no-sandbox","--disable-dev-shm-usage"]});
  report.chromiumVersion=browser.version();
  const {context,policy}=await controlledContext(browser);
  const page=await context.newPage();
  await page.setContent('<div class="mermaid"></div>');
  await page.addScriptTag({content:bundle.toString("utf8")});
  report.securityProbes=await page.evaluate(async()=>{
    window.mermaid.initialize({startOnLoad:false,securityLevel:"strict",flowchart:{htmlLabels:false}});
    const node=document.querySelector(".mermaid");
    node.textContent='flowchart LR\nA["safe"] --> B["safe"]\nclick A "javascript:window.probe=1" "attack"';
    await window.mermaid.run({nodes:[node]});
    const javascriptLinks=[...node.querySelectorAll("[href],[xlink\\:href]")].filter((element)=>/javascript:/i.test(element.getAttribute("href")||element.getAttribute("xlink:href")||""));
    return{strict:window.mermaid.mermaidAPI.getConfig().securityLevel==="strict",javascriptLinks:javascriptLinks.length,
      injectedCodeExecuted:window.probe===1,loadedVersions:window.__PORTAL_MERMAID_RUNTIME_INFO__};
  });
  assert.equal(report.securityProbes.strict,true);
  assert.equal(report.securityProbes.javascriptLinks,0);
  assert.equal(report.securityProbes.injectedCodeExecuted,false);
  assert.equal(policy.blockedRequests,0);
  // A harmless reserved-domain fetch proves the route fails before network IO.
  const denied=await page.evaluate(async()=>{try{await fetch("https://blocked.invalid/policy-probe");return false;}catch{return true;}});
  assert.equal(denied,true);
  assert.equal(policy.blockedRequests,1);
  report.securityProbes.httpRequestBlockedBeforeNetwork=true;
  const websocketDenied=await page.evaluate(()=>new Promise((resolve)=>{
    const socket=new WebSocket("wss://blocked.invalid/policy-probe");
    socket.onclose=()=>resolve(true);socket.onerror=()=>resolve(true);
    socket.onopen=()=>{socket.close();resolve(false);};
  }));
  assert.equal(websocketDenied,true);
  assert.equal(policy.blockedRequests,2);
  report.securityProbes.websocketBlockedBeforeNetwork=true;
  await browser.close();browser=null;
  report.sourceAfter=await sources();
  assert.deepEqual(report.sourceBefore,report.sourceAfter,"source changed during acceptance");
  report.outcome="PASS";
} catch(error) {
  report.outcome="FAIL";report.error=String(error.stack||error);
} finally {
  if(browser)await browser.close();
  await fs.writeFile(path.join(round,"report.json"),JSON.stringify(report,null,2)+"\n");
}
console.log(JSON.stringify({outcome:report.outcome,report:path.join(round,"report.json"),bundleSha256:report.bundleSha256,error:report.error}));
if(report.outcome!=="PASS")process.exitCode=1;
