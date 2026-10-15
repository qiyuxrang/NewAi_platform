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
const layoutVersion = "word-readable-v2";
let failureReason = "runtime_manifest_invalid";
let failureEvidence = {};
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
    await page.setContent('<style>html,body{margin:0;background:#fff}#canvas{display:inline-block;background:#fff}#canvas svg{display:block;max-width:none!important}#canvas .unit-title{font:700 18px "Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:#000;padding:8px 12px;box-sizing:border-box;overflow-wrap:anywhere}</style><main id="canvas"></main>', {waitUntil:"domcontentloaded"});
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
      failureEvidence = {};
      failureReason="diagram_path_invalid";
      const destination=await confined(root,figure.path);
      if (!destination.startsWith(root+path.sep) || path.extname(destination).toLowerCase()!==".png") throw new Error("unsafe diagram path");
      await fs.mkdir(path.dirname(destination),{recursive:true});
      const inputDiagram=sources.get(figure.id);
      const diagram=inputDiagram.source;
      const widthMm=figure.width_mm ?? 145;
      if (!Number.isFinite(widthMm) || widthMm<10 || widthMm>145) throw new Error("invalid diagram width");
      const binding={...bitmapBinding(figure,inputDiagram,runtimeBinding),layoutVersion,widthMm};
      const layoutPath=await confined(root,`.bitmap-cache/${sha256(JSON.stringify(binding))}.layout.json`);
      failureReason="diagram_cache_invalid";
      const cachedHash=await loadBitmap(root,binding,destination);
      let cachedLayout;
      if (cachedHash) {
        try {
          cachedLayout=JSON.parse(await fs.readFile(layoutPath,"utf8"));
          if (cachedLayout.version!==layoutVersion || !Array.isArray(cachedLayout.panels) || !cachedLayout.panels.length || cachedLayout.panels.length>2) cachedLayout=null;
          for (const [position,panel] of (cachedLayout?.panels || []).entries()) {
            const expectedPath=panel.index===1 ? figure.path : figure.path.replace(/\.png$/i,`-unit-${panel.index}.png`);
            if (panel.path!==expectedPath || panel.index!==position+1 || panel.total!==cachedLayout.panels.length
                || !Number.isFinite(panel.min_font_pt) || panel.min_font_pt<10.5
                || !Number.isFinite(panel.width_mm) || panel.width_mm<10 || panel.width_mm>widthMm
                || await loadBitmap(root,panel.index===1 ? binding : {...binding,panelIndex:panel.index},await confined(root,panel.path))!==panel.imageSha256) cachedLayout=null;
            if (!cachedLayout) break;
          }
        } catch(error) { if (["ENOENT","SyntaxError"].includes(error.code || error.name)) cachedLayout=null; else throw error; }
      }
      if (cachedHash && cachedLayout) {
        rendered+=1;
        evidence.push({figure_id:figure.id,sourceSha256:binding.sourceSha256,imageSha256:cachedHash,layout:cachedLayout});
        continue;
      }
      if (!page) await preparePage();
      failureReason="diagram_parse_or_anchor_failed";
      const layout=await page.evaluate(async ({diagram,anchor,widthMm})=>{
        const host=document.querySelector("#canvas"); host.replaceChildren();
        const graph=document.createElement("div"); graph.className="mermaid"; graph.textContent=diagram; host.append(graph);
        window.mermaid.initialize({startOnLoad:false,securityLevel:"strict",htmlLabels:false,theme:"base",themeVariables:{fontSize:"20px",primaryColor:"#E7F0FF",primaryBorderColor:"#246BCE",primaryTextColor:"#000000",secondaryColor:"#E5FAF5",secondaryTextColor:"#000000",tertiaryColor:"#FFF2D8",tertiaryTextColor:"#000000",textColor:"#000000",lineColor:"#246BCE"},fontFamily:"Microsoft YaHei, Noto Sans CJK SC, sans-serif",flowchart:{htmlLabels:false,curve:"linear",nodeSpacing:24,rankSpacing:32,padding:12},sequence:{actorFontSize:20,messageFontSize:20,noteFontSize:20,diagramMarginX:8,diagramMarginY:8}});
        await window.mermaid.parse(diagram);
        await window.mermaid.run({nodes:[graph]});
        if (window.mermaid.mermaidAPI.getConfig().securityLevel!=="strict") throw new Error("diagram security configuration changed");
        let svg=graph.querySelector("svg");
        if (!svg || svg.querySelector(".error-icon,.error-text")) throw new Error("invalid diagram SVG");
        if (anchor && !svg.textContent.includes(anchor)) throw new Error("report evidence anchor is not visible in diagram");
        await document.fonts.ready;
        const exposeClusterTitles=()=>{
          for(const label of svg.querySelectorAll(".cluster-label")){
            const background=getComputedStyle(label.closest(".cluster").querySelector("rect")).fill;
            const matrix=svg.getScreenCTM().inverse().multiply(label.getScreenCTM());
            label.setAttribute("transform",`matrix(${matrix.a},${matrix.b},${matrix.c},${matrix.d},${matrix.e},${matrix.f})`);
            for(const text of label.querySelectorAll("text")){
              text.style.paintOrder="stroke";text.style.stroke=background;text.style.strokeWidth="5px";
              text.style.strokeLinejoin="round";
            }
            // Mermaid draws cross-layer edges over group titles. Keep the same
            // title position and palette while letting the line pass behind it.
            svg.append(label);
          }
        };
        exposeClusterTitles();
        // Compare actual paper dimensions only when the authored direction does
        // not fit a readable unit. Prefer the authored layout on equal scores.
        const measure=()=>{
          const bounds=svg.getBBox(),width=Math.ceil(Math.max(320,bounds.width+24));
          const widthOnPaper=Math.min(widthMm,width*25.4/96);
          const text=[...svg.querySelectorAll("text")].filter(node=>node.textContent.trim());
          const font=Math.min(18,...text.map(node=>parseFloat(getComputedStyle(node).fontSize)));
          const minFontPt=font*widthOnPaper*72/25.4/width;
          return {minFontPt,heightMm:(bounds.height+24)*widthOnPaper/width,
            labelCount:text.length,nodeCount:svg.querySelectorAll(".node").length,
            edgeCount:svg.querySelectorAll(".edgePath,.flowchart-link,.messageLine0,.messageLine1").length};
        };
        const sourceDirection=diagram.match(/^\s*flowchart\s+(TB|TD|BT|LR|RL)\b/)?.[1] || "sequence";
        let direction=sourceDirection;
        const original=measure(),directionCandidates=[{direction:sourceDirection,...original}];
        // ponytail: one orthogonal candidate; broader search only for proven layout failures.
        if (["TB","TD","LR","RL"].includes(sourceDirection) && (original.minFontPt<10.5 || original.heightMm>190)) {
          const alternative=["LR","RL"].includes(sourceDirection) ? "TB" : "LR";
          const renderDirection=async(value)=>{
            graph.removeAttribute("data-processed");graph.textContent=diagram.replace(/^(\s*flowchart\s+)(?:TB|TD|LR|RL)\b/,"$1"+value);
            await window.mermaid.run({nodes:[graph]});svg=graph.querySelector("svg");await document.fonts.ready;
            if (!svg || (anchor && !svg.textContent.includes(anchor))) throw new Error("invalid relayout");
            exposeClusterTitles();
          };
          await renderDirection(alternative);
          const candidate=measure();directionCandidates.push({direction:alternative,...candidate});
          const sameContent=["labelCount","nodeCount","edgeCount"].every(key=>candidate[key]===original[key]);
          if (sameContent && candidate.minFontPt>=10.5 && (original.minFontPt<10.5 ||
              Math.ceil(candidate.heightMm/190)<Math.ceil(original.heightMm/190))) direction=alternative;
          else await renderDirection(sourceDirection);
        }
        const bounds=svg.getBBox(),padding=12;
        const width=Math.ceil(Math.max(320,bounds.width+padding*2));
        const outputWidthMm=Math.min(widthMm,width*25.4/96);
        const text=[...svg.querySelectorAll("text")].filter(node=>node.textContent.trim());
        if (!text.length) throw new Error("missing diagram labels");
        const font=Math.min(18,...text.map(node=>parseFloat(getComputedStyle(node).fontSize)));
        const minFontPt=font*outputWidthMm*72/25.4/width;
        const unreadable=(detail,extra={})=>({failure:{detail,sourceDirection,direction,directionCandidates,minFontPt,...extra}});
        if (!Number.isFinite(minFontPt) || minFontPt<10.5) return unreadable("font_below_minimum");
        // Inspect rendered rows, not guessed character widths. Only reject a
        // continuous authored number; separate values and English wraps remain valid.
        const numericTokens=new Set(diagram.match(/\d+(?:[.．]\d+)*/g) || []);
        let numericSplitCount=0;
        for(const label of svg.querySelectorAll(".node text")){
          const rows=[...label.children].filter(node=>node.tagName.toLowerCase()==="tspan").map(node=>node.textContent.trim());
          for(let index=1;index<rows.length;index+=1){
            const before=rows[index-1].match(/\d+(?:[.．]\d*)?$/)?.[0];
            const after=rows[index].match(/^[.．]?\d+/)?.[0];
            if(before && after && numericTokens.has(before+after)) numericSplitCount+=1;
          }
        }
        if(numericSplitCount) return unreadable("numeric_token_split",{numericSplitCount});
        // Cuts never cross a node, actor, annotation or visible label. Repeating
        // the last row preserves the entry/exit context of cross-unit arrows.
        const protectedBoxes=[...svg.querySelectorAll(".node,.actor,.note,text")].map(node=>{
          const box=node.getBBox(),matrix=svg.getScreenCTM().inverse().multiply(node.getScreenCTM());
          const first=new DOMPoint(box.x,box.y).matrixTransform(matrix),last=new DOMPoint(box.x+box.width,box.y+box.height).matrixTransform(matrix);
          return {x:first.x,y:first.y,width:last.x-first.x,height:last.y-first.y,isNode:node.matches(".node,.actor,.note")};
        })
          .filter(box=>box.width>0 && box.height>0).map(box=>({start:box.y-4,end:box.y+box.height+4,isNode:box.isNode})).sort((a,b)=>a.start-b.start);
        const bands=[];
        for(const box of protectedBoxes){const last=bands.at(-1); if(last && box.start<=last.end){last.end=Math.max(last.end,box.end);last.isNode ||= box.isNode;}else bands.push({...box});}
        const maximumHeight=190*96/25.4*width/(outputWidthMm*96/25.4)-48;
        const regions=[];let start=bounds.y-padding,end=bounds.y+bounds.height+padding;
        while(end-start>maximumHeight){
          const candidates=bands.slice(0,-1).map((band,index)=>({cut:(band.end+bands[index+1].start)/2,index}))
            .filter(item=>item.cut>start+maximumHeight*.35 && item.cut<=start+maximumHeight);
          if(!candidates.length) return unreadable("no_label_safe_cut");
          const chosen=candidates.at(-1);regions.push({start,end:chosen.cut});
          const lastNodeBand=bands.slice(0,chosen.index+1).findLast(band=>band.isNode);
          const repeated=(lastNodeBand?.start ?? bands[chosen.index].start)-padding;
          start=repeated>start+maximumHeight*.2 ? repeated : chosen.cut-12;
        }
        regions.push({start,end});
        if(regions.length>2) return unreadable("too_many_reading_units",{readingUnitCount:regions.length,maximumReadingUnits:2});
        if (protectedBoxes.some(box=>!regions.some(region=>box.start>=region.start && box.end<=region.end))) return unreadable("reading_unit_cuts_label");
        const sourceSvg=svg.cloneNode(true);host.replaceChildren();host.style.width=width+"px";
        const panels=regions.map((region,index)=>{
          const unit=document.createElement("section");unit.id="unit-"+(index+1);
          const heading=document.createElement("div");heading.className="unit-title";
          heading.textContent=regions.length===1 ? "" : `阅读单元 ${index+1}/${regions.length}${index ? " · 承接上一单元" : ""}${index<regions.length-1 ? " · 接下一单元" : ""}`;
          if(regions.length>1)unit.append(heading);
          const image=sourceSvg.cloneNode(true);image.setAttribute("viewBox",`${bounds.x-padding} ${region.start} ${width} ${region.end-region.start}`);
          image.setAttribute("width",width);image.setAttribute("height",Math.ceil(region.end-region.start));image.style.width=width+"px";image.style.height=Math.ceil(region.end-region.start)+"px";
          unit.append(image);host.append(unit);
          return {index:index+1,total:regions.length,width_mm:outputWidthMm,min_font_pt:minFontPt,css_width:width,css_height:unit.getBoundingClientRect().height};
        });
        return {panels,direction,sourceDirection,directionCandidates,labelCount:text.length,nodeCount:svg.querySelectorAll(".node").length,
          edgeCount:svg.querySelectorAll(".edgePath,.flowchart-link,.messageLine0,.messageLine1").length,
          labelsFullyContained:true,contentBounds:{width:bounds.width,height:bounds.height},minFontPt};
      },{diagram,anchor:inputDiagram.anchor_text,widthMm}).catch(error=>{
        if (/diagram requires narrower reading units|diagram cannot split without cutting labels|reading unit cuts a visible label/.test(error.message)) failureReason="diagram_layout_unreadable";
        throw error;
      });
      if(layout.failure){
        failureReason="diagram_layout_unreadable";
        failureEvidence={figure_id:figure.id,...layout.failure};
        throw new Error("diagram layout unreadable");
      }
      failureReason="diagram_bitmap_failed";
      for(const panel of layout.panels){
        panel.path=panel.index===1 ? figure.path : figure.path.replace(/\.png$/i,`-unit-${panel.index}.png`);
        const panelDestination=await confined(root,panel.path);
        await page.locator(`#unit-${panel.index}`).screenshot({path:panelDestination,type:"png"});
        panel.imageSha256=await saveBitmap(root,panel.index===1 ? binding : {...binding,panelIndex:panel.index},panelDestination);
      }
      layout.version=layoutVersion;
      await fs.writeFile(layoutPath,JSON.stringify(layout));
      if (networkPolicy.blockedRequests) { failureReason="diagram_network_blocked"; throw new Error("network policy violated"); }
      const imageSha256=layout.panels[0].imageSha256;
      rendered+=1;
      evidence.push({figure_id:figure.id,sourceSha256:createHash("sha256").update(diagram).digest("hex"),
        imageSha256,layout});
    }
  } finally { if (browser) await browser.close(); }
  if (networkPolicy.blockedRequests) throw new Error("diagram attempted an external network request");
  process.stdout.write(JSON.stringify({rendered,sourcePersisted:false,engine:`mermaid-js-${runtimeVersions.mermaid}`,
    bundleSha256:manifest.bundleSha256,manifestSha256,runtimeVersions,layoutVersion,figures:evidence,securityLevel:"strict",blockedNetworkRequests:networkPolicy.blockedRequests}));
}
main().catch(()=>{process.stderr.write(JSON.stringify({stage:"diagram_render",reason:failureReason,...failureEvidence})+"\n");process.exit(2);});
