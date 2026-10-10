import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { readVerifiedBundle } from "./bundle-contract.mjs";
import { controlledContext } from "./browser-policy.mjs";

const runtimeDirectory = path.dirname(fileURLToPath(import.meta.url));
async function main() {
  if (process.argv.length !== 4) throw new Error("usage: render.mjs content.json private-diagrams.json");
  const contentPath = path.resolve(process.argv[2]);
  const root = path.dirname(contentPath);
  const content = JSON.parse(await fs.readFile(contentPath, "utf8"));
  const figures = content.blocks.filter((block) => block.type === "figure");
  const sourcePath = path.resolve(process.argv[3]);
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
  const {manifest,manifestSha256,bundle} = await readVerifiedBundle(path.join(runtimeDirectory,"dist"));
  const browser = await chromium.launch({headless:true, executablePath:process.env.PORTAL_CHROMIUM_PATH || undefined,
    args:["--no-sandbox","--disable-dev-shm-usage"]});
  let rendered = 0;
  let networkPolicy;
  let runtimeVersions;
  try {
    const {context,policy} = await controlledContext(browser,{viewport:{width:1600,height:900},deviceScaleFactor:1.5});
    networkPolicy = policy;
    const page = await context.newPage();
    await page.setContent('<style>html,body{margin:0;background:#F8FBFF}#canvas{box-sizing:border-box;width:1600px;height:900px;padding:34px 50px 40px;overflow:hidden}#canvas .mermaid{display:flex;align-items:center;justify-content:center;width:1500px;height:760px}#canvas svg{width:1460px!important;height:700px!important;max-width:none!important}</style><main id="canvas"></main>', {waitUntil:"domcontentloaded"});
    // Load exactly the verified bytes; never use Mermaid's legacy prebundled UMD.
    await page.addScriptTag({content:bundle.toString("utf8")});
    runtimeVersions = await page.evaluate(()=>window.__PORTAL_MERMAID_RUNTIME_INFO__);
    for (const name of ["mermaid","katex","lodash-es"]) {
      if (runtimeVersions[name] !== manifest.versions[name]) throw new Error("loaded runtime version mismatch");
    }
    for (let index=0; index<figures.length; index+=1) {
      const figure=figures[index];
      const destination=path.resolve(root,figure.path);
      if (!destination.startsWith(root+path.sep) || path.extname(destination).toLowerCase()!==".png") throw new Error("unsafe diagram path");
      await fs.mkdir(path.dirname(destination),{recursive:true});
      const inputDiagram=sources.get(figure.id);
      const diagram=inputDiagram.source;
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
      await page.locator("#canvas").screenshot({path:destination,type:"png"}); rendered+=1;
      evidence.push({figure_id:figure.id,sourceSha256:createHash("sha256").update(diagram).digest("hex"),
        imageSha256:createHash("sha256").update(await fs.readFile(destination)).digest("hex")});
    }
  } finally { await browser.close(); }
  if (networkPolicy.blockedRequests) throw new Error("diagram attempted an external network request");
  process.stdout.write(JSON.stringify({rendered,sourcePersisted:false,engine:`mermaid-js-${runtimeVersions.mermaid}`,
    bundleSha256:manifest.bundleSha256,manifestSha256,runtimeVersions,figures:evidence,securityLevel:"strict",blockedNetworkRequests:networkPolicy.blockedRequests}));
}
main().catch(()=>{process.stderr.write("Mermaid rendering failed.\n");process.exit(2);});
