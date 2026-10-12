import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { readVerifiedBundle } from "./bundle-contract.mjs";
import { controlledContext } from "./browser-policy.mjs";
import { bitmapBinding, confined, loadBitmap, saveBitmap, sha256 } from "./bitmap-cache.mjs";

const runtimeDirectory = path.dirname(fileURLToPath(import.meta.url));
let failureReason = "runtime_manifest_invalid";
async function main() {
  const {manifest,manifestSha256,bundle} = await readVerifiedBundle(path.join(runtimeDirectory,"dist"));
  const rendererSha256=sha256(Buffer.concat(await Promise.all(
    ["render.mjs","bitmap-cache.mjs","browser-policy.mjs","bundle-contract.mjs"].map((name)=>fs.readFile(path.join(runtimeDirectory,name))))));
  failureReason="chromium_unavailable";
  const chromiumPath=process.env.PORTAL_CHROMIUM_PATH;
  if (!chromiumPath || !(await fs.stat(chromiumPath)).isFile()) throw new Error("missing Chromium");
  const runtimeBinding={bundleSha256:manifest.bundleSha256,manifestSha256,rendererSha256,
    nodeSha256:sha256(await fs.readFile(process.execPath)),chromiumSha256:sha256(await fs.readFile(chromiumPath))};
  if (process.argv.length===3 && process.argv[2]==="--preflight") {
    process.stdout.write(JSON.stringify({...runtimeBinding,runtimeVersions:manifest.versions})); return;
  }
  failureReason="diagram_input_invalid";
  if (process.argv.length !== 4) throw new Error("usage: render.mjs content.json private-diagrams.json");
  const contentPath = path.resolve(process.argv[2]);
  const root = path.dirname(contentPath);
  const content = JSON.parse(await fs.readFile(contentPath, "utf8"));
  const figures = content.blocks.filter((block) => block.type === "figure");
  const sourcePath = await confined(root,path.relative(root,path.resolve(process.argv[3])));
  if (!sourcePath.startsWith(root+path.sep) || sourcePath===contentPath) throw new Error("unsafe private diagram input");
  const input = JSON.parse(await fs.readFile(sourcePath,"utf8"));
  await fs.unlink(sourcePath);
  if (!Array.isArray(input.diagrams) || input.diagrams.length!==figures.length) throw new Error("missing diagram sources");
  const sources = new Map();
  const distinct = new Set();
  for (const diagram of input.diagrams) {
    if (typeof diagram.figure_id!=="string" || sources.has(diagram.figure_id)
        || typeof diagram.source!=="string" || !diagram.source.trim() || diagram.source.length>6000
        || !/^\s*(?:flowchart\s+(?:TB|TD|BT|RL|LR)|sequenceDiagram)\b/.test(diagram.source)
        || /%%|https?:\/\/|javascript:|<|\b(?:click|style|classDef|linkStyle)\b/i.test(diagram.source)) throw new Error("invalid or unsafe diagram source");
    const normalized=diagram.source.replace(/\s+/g,"");
    if (distinct.has(normalized)) throw new Error("duplicate diagram source");
    distinct.add(normalized);sources.set(diagram.figure_id,diagram);
  }
  if (new Set(figures.map((figure)=>figure.id)).size!==figures.length
      || figures.some((figure)=>!sources.has(figure.id))) throw new Error("diagram source binding mismatch");
  const evidence=[];
  let browser;
  let rendered = 0;
  let networkPolicy={blockedRequests:0};
  let runtimeVersions=Object.fromEntries(["mermaid","katex","lodash-es"].map((name)=>[name,manifest.versions[name]]));
  let page;
  async function preparePage() {
    failureReason="chromium_launch_failed";
    browser = await chromium.launch({headless:true, executablePath:chromiumPath,
      args:["--no-sandbox","--disable-dev-shm-usage"]});
    const {context,policy} = await controlledContext(browser,{viewport:{width:1600,height:900},deviceScaleFactor:1.5});
    networkPolicy = policy;
    page = await context.newPage();
    await page.setContent('<style>html,body{margin:0;background:#F8FBFF}#canvas{box-sizing:border-box;width:1600px;height:900px;padding:34px 50px 40px;overflow:hidden}#canvas .mermaid{display:flex;align-items:center;justify-content:center;width:1500px;height:760px}#canvas svg{width:1460px!important;height:700px!important;max-width:none!important}</style><main id="canvas"></main>', {waitUntil:"domcontentloaded"});
    // Load exactly the verified bytes; never use Mermaid's legacy prebundled UMD.
    await page.addScriptTag({content:bundle.toString("utf8")});
    runtimeVersions = await page.evaluate(()=>window.__PORTAL_MERMAID_RUNTIME_INFO__);
    for (const name of ["mermaid","katex","lodash-es"]) {
      if (runtimeVersions[name] !== manifest.versions[name]) throw new Error("loaded runtime version mismatch");
    }
  }
  try {
    for (let index=0; index<figures.length; index+=1) {
      const figure=figures[index];
      failureReason="diagram_path_invalid";
      const destination=await confined(root,figure.path);
      if (!destination.startsWith(root+path.sep) || path.extname(destination).toLowerCase()!==".png") throw new Error("unsafe diagram path");
      await fs.mkdir(path.dirname(destination),{recursive:true});
      const inputDiagram=sources.get(figure.id);
      const diagram=inputDiagram.source;
      const binding=bitmapBinding(figure,inputDiagram,runtimeBinding);
      failureReason="diagram_cache_invalid";
      const cachedHash=await loadBitmap(root,binding,destination);
      if (cachedHash) {
        rendered+=1;
        evidence.push({figure_id:figure.id,sourceSha256:binding.sourceSha256,imageSha256:cachedHash});
        continue;
      }
      if (!page) await preparePage();
      failureReason="diagram_parse_or_anchor_failed";
      await page.evaluate(async ({diagram,title,anchor})=>{
        const host=document.querySelector("#canvas"); host.replaceChildren();
        const heading=document.createElement("h1"); heading.textContent=title;
        heading.style.cssText="font:700 28px 'Microsoft YaHei','Noto Sans CJK SC',sans-serif;color:#000000;text-align:center;margin:8px 0 18px";
        const graph=document.createElement("div"); graph.className="mermaid"; graph.textContent=diagram; host.append(heading,graph);
        window.mermaid.initialize({startOnLoad:false,securityLevel:"strict",theme:"base",themeVariables:{primaryColor:"#E7F0FF",primaryBorderColor:"#246BCE",primaryTextColor:"#000000",secondaryColor:"#E5FAF5",secondaryTextColor:"#000000",tertiaryColor:"#FFF2D8",tertiaryTextColor:"#000000",textColor:"#000000",lineColor:"#246BCE"},fontFamily:"Microsoft YaHei, Noto Sans CJK SC, sans-serif",flowchart:{htmlLabels:false,curve:"basis",nodeSpacing:42,rankSpacing:58}});
        await window.mermaid.parse(diagram);
        await window.mermaid.run({nodes:[graph]});
        if (window.mermaid.mermaidAPI.getConfig().securityLevel!=="strict") throw new Error("diagram security configuration changed");
        const svg=graph.querySelector("svg");
        if (!svg || svg.querySelector(".error-icon,.error-text")) throw new Error("invalid diagram SVG");
        if (anchor && !svg.textContent.includes(anchor)) throw new Error("report evidence anchor is not visible in diagram");
        svg.style.cssText+="background:#F8FBFF;border:1px solid #D7E3F2;border-radius:14px;padding:22px;box-sizing:border-box";
      },{diagram,title:figure.caption,anchor:inputDiagram.anchor_text});
      failureReason="diagram_bitmap_failed";
      await page.locator("#canvas").screenshot({path:destination,type:"png"});
      if (networkPolicy.blockedRequests) { failureReason="diagram_network_blocked"; throw new Error("network policy violated"); }
      const imageSha256=await saveBitmap(root,binding,destination);
      rendered+=1;
      evidence.push({figure_id:figure.id,sourceSha256:createHash("sha256").update(diagram).digest("hex"),
        imageSha256});
    }
  } finally { if (browser) await browser.close(); }
  if (networkPolicy.blockedRequests) throw new Error("diagram attempted an external network request");
  process.stdout.write(JSON.stringify({rendered,sourcePersisted:false,engine:`mermaid-js-${runtimeVersions.mermaid}`,
    bundleSha256:manifest.bundleSha256,manifestSha256,runtimeVersions,figures:evidence,securityLevel:"strict",blockedNetworkRequests:networkPolicy.blockedRequests}));
}
main().catch(()=>{process.stderr.write(JSON.stringify({stage:"diagram_render",reason:failureReason})+"\n");process.exit(2);});
