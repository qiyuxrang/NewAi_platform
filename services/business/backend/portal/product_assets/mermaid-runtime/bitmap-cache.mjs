import fs from "node:fs/promises";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";

export const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const pngSignature = Buffer.from([137,80,78,71,13,10,26,10]);

export async function confined(root, relative) {
  root = await fs.realpath(root);
  if (typeof relative !== "string" || !relative || path.isAbsolute(relative)
      || relative.split(/[\\/]/).some((part)=>part === "..")) throw new Error("unsafe diagram path");
  const target = path.resolve(root,relative);
  if (!target.startsWith(root+path.sep)) throw new Error("unsafe diagram path");
  for (let current=target; current!==root; current=path.dirname(current)) {
    try {
      if ((await fs.lstat(current)).isSymbolicLink()) throw new Error("unsafe diagram link");
      if (!(await fs.realpath(current)).startsWith(root+path.sep)) throw new Error("unsafe diagram path");
    } catch (error) { if (error.code !== "ENOENT") throw error; }
  }
  return target;
}

async function atomicWrite(destination, data) {
  const temporary=destination+"."+randomUUID()+".tmp";
  try { await fs.writeFile(temporary,data,{flag:"wx"}); await fs.rename(temporary,destination); }
  finally { await fs.unlink(temporary).catch((error)=>{if (error.code!=="ENOENT") throw error;}); }
}

export function bitmapBinding(figure, diagram, runtime) {
  // Only hashes survive the private input's deletion, including the caption
  // and visible anchor. A changed render policy never reuses old pixels.
  return {schemaVersion:1, figureSha256:sha256(figure.id), sourceSha256:sha256(diagram.source),
    titleSha256:sha256(figure.caption || ""), anchorSha256:sha256(diagram.anchor_text || ""), ...runtime};
}

export async function loadBitmap(root, binding, destination) {
  try {
    const key=sha256(JSON.stringify(binding));
    const metadata=JSON.parse(await fs.readFile(await confined(root,`.bitmap-cache/${key}.json`),"utf8"));
    if (JSON.stringify(metadata.binding)!==JSON.stringify(binding)) return null;
    const image=await fs.readFile(await confined(root,`.bitmap-cache/${key}.png`));
    if (!image.subarray(0,8).equals(pngSignature) || sha256(image)!==metadata.imageSha256) return null;
    await fs.mkdir(path.dirname(destination),{recursive:true});
    await confined(root,path.relative(root,destination));
    await atomicWrite(destination,image);
    return metadata.imageSha256;
  } catch (error) {
    if (["ENOENT","SyntaxError"].includes(error.code || error.name)) return null;
    // Unsafe path entries must fail closed, never get overwritten as misses.
    throw error;
  }
}

export async function saveBitmap(root, binding, destination) {
  const image=await fs.readFile(destination);
  if (!image.subarray(0,8).equals(pngSignature)) throw new Error("invalid bitmap");
  const key=sha256(JSON.stringify(binding));
  const cache=await confined(root,".bitmap-cache");
  await fs.mkdir(cache,{recursive:true});
  const imageSha256=sha256(image);
  await atomicWrite(await confined(root,`.bitmap-cache/${key}.png`),image);
  await atomicWrite(await confined(root,`.bitmap-cache/${key}.json`),JSON.stringify({binding,imageSha256}));
  return imageSha256;
}
