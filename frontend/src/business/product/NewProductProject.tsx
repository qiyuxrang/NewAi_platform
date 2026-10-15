import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { ApiError } from "../api";
import { CenterLink, Field } from "../shared";
import { createTask, getTask, updateTask, uploadSource, type CreateTask, type DocumentTask } from "./product-api";
import { LoadState, ProductIcon } from "./workbench-shared";
import { formatBytes, goProduct, productError, projectUrl, useProductOverview, useUnsavedWarning } from "./workbench-state";
import './project-analysis.css';
import "./product-clean-layout.css";

interface Submission { body: CreateTask; key: string; task: DocumentTask | null; remaining: File[]; equipment: File | null; start: boolean }
export default function NewProductProject() {
  const filePicker = useRef(false);
  const { data, error: loadError, reload } = useProductOverview("", true, filePicker);
  const [title, setTitle] = useState("");
  const [requirements, setRequirements] = useState("");
  const [background, setBackground] = useState("");
  const [conditions, setConditions] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [equipment, setEquipment] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [uploadProgress, setUploadProgress] = useState({ completed: 0, total: 0 });
  const [pending, setPending] = useState(false);
  const [createdId, setCreatedId] = useState("");
  const [leaving, setLeaving] = useState(false);
  const submission = useRef<Submission | null>(null);
  const lock = useRef(false);
  const request = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const equipmentInput = useRef<HTMLInputElement>(null);
  const [dragTarget, setDragTarget] = useState("");
  useUnsavedWarning(!leaving && Boolean(title || requirements || background || conditions || files.length || equipment || pending));
  useEffect(() => () => request.current?.abort(), []);

  function finishFileSelection() {
    filePicker.current = false;
    reload();
  }

  function registerFileInput(element: HTMLInputElement | null) {
    if (!element) return;
    element.addEventListener("cancel", finishFileSelection);
    return () => element.removeEventListener("cancel", finishFileSelection);
  }

  function addFiles(next: File[]) {
    if (pending || busy || !data) return;
    const accepted = data.capabilities.upload_extensions;
    const invalid = next.find(file => !accepted.some(ext => file.name.toLowerCase().endsWith(ext)) || file.size > data.capabilities.upload_max_bytes || file.size === 0);
    if (invalid) { setError(`“${invalid.name}”格式、大小或内容不符合要求。支持 ${accepted.join("、")}，单个文件最多 ${formatBytes(data.capabilities.upload_max_bytes)}，不可为空。`); return; }
    setFiles(current => [...current, ...next.filter(file => !current.some(old => old.name === file.name && old.size === file.size && old.lastModified === file.lastModified))]);
    setError("");
  }
  function chooseEquipment(file: File | null) {
    if (!file || !data || pending || busy) return;
    if (!data.capabilities.upload_extensions.some(ext => file.name.toLowerCase().endsWith(ext)) || !file.size || file.size > data.capabilities.upload_max_bytes) {
      setError('设备清单格式、大小或内容不符合要求，请选择受支持的非空文件。'); return;
    }
    setEquipment(file); setError('');
  }
  function leave(id: string) {
    flushSync(() => setLeaving(true));
    goProduct(projectUrl(id));
  }
  async function submit(start: boolean) {
    if (lock.current || !data) return;
    if (!submission.current && (!equipment || !files.length)) { setError('请上传一份设备清单和至少一份项目背景材料。'); return; }
    lock.current = true; setBusy(true); setError("");
    const controller = new AbortController(); request.current = controller;
    const projectName = title.trim() || equipment?.name.replace(/\.[^.]+$/, '').slice(0, 200) || '资料生成项目';
    if (!submission.current) {
      setUploadProgress({ completed: 0, total: files.length + 1 });
      submission.current = { key: crypto.randomUUID(), task: null, remaining: [...(equipment ? [equipment] : []), ...files], equipment, start,
        body: { title: projectName, intake_mode: 'equipment_background', output_families: ['technical-solution', 'feasibility', 'presentation'], input: { project: projectName, requirements: ['根据上传的乙方设备清单和甲方调研、项目需求及背景材料，完整编制项目蓝图、技术方案、可行性研究报告和基于两份报告的汇报演示文稿。技术方案正文不少于50000字、Mermaid图不少于15张；可行性研究报告正文不少于70000字、Mermaid图不少于20张。保持来源一致，不编造缺失参数，资料不足处明确列为待确认。', requirements.trim()].filter(Boolean).join('\n'), background: background.trim(), conditions: conditions.split("\n").map(value => value.trim()).filter(Boolean), items: [] } } };
    }
    const record = submission.current;
    setPending(true);
    try {
      if (!record.task) { setProgress("正在创建项目…"); record.task = await createTask(record.body, record.key, controller.signal); setCreatedId(record.task.id); }
      let currentTask: DocumentTask = record.task;
      while (record.remaining.length) {
        const file = record.remaining[0];
        const previousSourceIds = new Set(currentTask.sources.map(source => source.id));
        setProgress(`正在上传并解析 ${file.name}…`);
        try {
          currentTask = await uploadSource(currentTask.id, file, currentTask.version, controller.signal, file === record.equipment ? 'equipment' : 'background');
        } catch (reason) {
          // A lost HTTP response may follow a successful upload. Reconcile only an
          // exact, newly created name/size/hash snapshot; never blindly repeat it.
          if (controller.signal.aborted) throw reason;
          const fresh: DocumentTask | null = await getTask(currentTask.id, controller.signal).catch(() => null);
          const hash = crypto.subtle ? Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()))).map(byte => byte.toString(16).padStart(2, "0")).join("") : "";
          if (fresh && hash && fresh.sources.some(source => !previousSourceIds.has(source.id) && source.original_name === file.name && source.size === file.size && source.sha256 === hash && source.purpose === (file === record.equipment ? 'equipment' : 'background'))) currentTask = fresh;
          else throw reason;
        }
        record.task = currentTask;
        record.remaining = record.remaining.slice(1);
        setUploadProgress(value => ({ ...value, completed: value.total - record.remaining.length }));
        setFiles(record.remaining.filter(item => item !== record.equipment));
        if (!record.remaining.includes(record.equipment as File)) setEquipment(null);
      }
      if (record.start) {
        currentTask = await getTask(currentTask.id, controller.signal);
        record.task = currentTask;
        if (!['QUEUED', 'RUNNING', 'COMPLETED'].includes(currentTask.state) && !currentTask.blueprint) {
          setProgress("资料已保存，正在提交知识检索和蓝图生成…");
          await updateTask(currentTask.id, "queue/", { expected_version: currentTask.version, action: "start" }, controller.signal);
        }
      }
      if (!controller.signal.aborted) leave(currentTask.id);
    } catch (reason) {
      if (!controller.signal.aborted) {
        setError(productError(reason));
        if (reason instanceof ApiError && reason.status === 400 && !record.task) { submission.current = null; setPending(false); }
      }
    } finally { lock.current = false; if (!controller.signal.aborted) { setBusy(false); setProgress(""); } }
  }
  if (!data) return <LoadState error={loadError} reload={reload}/>;
  const canGenerate = data.capabilities.model_generation;
  return <div className="pd-workspace pd-clean-layout wb-new-project"><div className="pd-page-title"><div className="pd-intake-title"><span className="pd-intake-title-icon"><ProductIcon name="layers"/></span><div><h1>从项目资料，开始一次完整交付</h1><p>上传设备清单与项目背景，一起完成技术方案、可研报告和汇报 PPT。</p></div></div><CenterLink href="/centers/product/projects" className="pd-back-link">查看历史项目 →</CenterLink></div>
    <div className="pd-new-layout"><form className="pd-panel pd-project-form" onSubmit={event => { event.preventDefault(); void submit(canGenerate); }}>
      <div className="pd-panel-heading"><h3>上传项目资料</h3><span className="pd-intake-count">已选择 {files.length + Number(!!equipment)} 份资料</span></div>
      {error && <div className="pd-feedback" role="alert">{error}</div>}
      {pending && !busy && <p role="note" className="pd-service-note">{createdId ? `项目已保存，剩余 ${submission.current?.remaining.length || 0} 份资料待上传；如资料已齐全，重试将继续提交生成。已确认成功的附件不会重复上传。` : "正在确认上次创建结果，重试将复用相同请求，避免重复项目。"}</p>}
      <fieldset disabled={busy || pending} className="pd-form-fields">
        <div className="pd-intake-uploads">
          <section className="pd-intake-upload-card" aria-label="乙方设备清单上传">
            <div className="pd-intake-card-heading"><h3>乙方设备清单</h3><span className={equipment ? "is-selected" : ""}>{equipment ? "已选择" : "必需 · 1 份"}</span></div>
            <div className="pd-intake-dropzone" data-dragging={dragTarget === "equipment"} onDragOver={event => { event.preventDefault(); if (!busy && !pending) setDragTarget("equipment"); }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragTarget(""); }} onDrop={event => { event.preventDefault(); setDragTarget(""); if (busy || pending) return; const dropped = Array.from(event.dataTransfer.files); if (dropped.length !== 1) { setError("设备清单每次请选择一份文件，背景材料可在右侧上传多份。"); return; } chooseEquipment(dropped[0]); }}>
              <div className="pd-intake-dropzone-heading"><span className="pd-intake-upload-icon"><ProductIcon name="file"/></span><div><strong>上传设备清单</strong><p>提取设备名称、数量与单位</p></div></div><button className="button secondary" type="button" onClick={() => equipmentInput.current?.click()}>{equipment ? "更换设备清单" : "选择设备清单"}</button><small>也可拖拽一份文件到这里</small>
              <input ref={element => { equipmentInput.current = element; return registerFileInput(element); }} id="equipment-source" type="file" className="sr-only" aria-label="选择设备清单文件" accept={data.capabilities.upload_extensions.join(',')} onClick={() => { filePicker.current = true; }} onChange={event => { chooseEquipment(event.target.files?.[0] || null); event.target.value = ''; finishFileSelection(); }}/>
            </div>
            {equipment && <ul className="pd-upload-list" aria-label="待上传设备清单"><li><ProductIcon name="file"/><div><strong title={equipment.name}>{equipment.name}</strong><small>{formatBytes(equipment.size)}</small></div><button className="text-button" type="button" onClick={() => setEquipment(null)}>移除设备清单</button></li></ul>}
          </section>
          <section className="pd-intake-upload-card" aria-label="项目背景材料上传">
            <div className="pd-intake-card-heading"><h3>项目背景材料</h3><span className={files.length ? "is-selected" : ""}>{files.length ? `${files.length} 份已选择` : "必需 · 支持多份"}</span></div>
            <div className="pd-intake-dropzone" data-dragging={dragTarget === "background"} onDragOver={event => { event.preventDefault(); if (!busy && !pending) setDragTarget("background"); }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragTarget(""); }} onDrop={event => { event.preventDefault(); setDragTarget(""); addFiles(Array.from(event.dataTransfer.files)); }}>
              <div className="pd-intake-dropzone-heading"><span className="pd-intake-upload-icon"><ProductIcon name="folder"/></span><div><strong>上传项目背景</strong><p>补充调研、需求与项目现状</p></div></div><button className="button secondary" type="button" onClick={() => input.current?.click()}>选择背景材料</button><small>支持拖拽多份文件到这里</small>
              <input ref={element => { input.current = element; return registerFileInput(element); }} type="file" className="sr-only" aria-label="选择项目资料文件" multiple accept={data.capabilities.upload_extensions.join(",")} onClick={() => { filePicker.current = true; }} onChange={event => { addFiles(Array.from(event.target.files || [])); event.target.value = ""; finishFileSelection(); }}/>
            </div>
            {files.length > 0 && <ul className="pd-upload-list" aria-label="待上传项目资料">{files.map((file, index) => <li key={`${file.name}-${index}`}><ProductIcon name="file"/><div><strong title={file.name}>{file.name}</strong><small>{formatBytes(file.size)}</small></div><button type="button" className="text-button" aria-label={`移除 ${file.name}`} onClick={() => setFiles(values => values.filter((_, i) => i !== index))}>移除</button></li>)}</ul>}
          </section>
        </div>
        <p className="pd-intake-formats">支持 {data.capabilities.upload_extensions.join(" / ")} · 单个文件最多 {formatBytes(data.capabilities.upload_max_bytes)}</p>
        <details className="pd-optional-project-fields"><summary>补充项目名称与要求（选填）</summary>
        <Field id="new-project-title" label="项目名称" hint="不填写时使用设备清单文件名作为历史项目名称。"><input id="new-project-title" value={title} onChange={event => setTitle(event.target.value)} maxLength={200} placeholder="例如：榆林选煤厂供配电系统建设项目"/></Field>
        <Field id="new-project-requirements" label="额外编制要求" hint="甲方需求已在背景文件中说明时，可不重复填写。"><textarea id="new-project-requirements" value={requirements} onChange={event => setRequirements(event.target.value)} maxLength={10000} rows={4} placeholder="补充需要强调的建设目标或编制要求…"/></Field>
        <div className="pd-form-columns"><Field id="new-project-background" label="项目背景"><textarea id="new-project-background" value={background} onChange={event => setBackground(event.target.value)} maxLength={10000} rows={3} placeholder="现状、使用场景或已有基础…"/></Field><Field id="new-project-conditions" label="约束条件" hint="每行一项，生成蓝图时保留这些条件。"><textarea id="new-project-conditions" value={conditions} onChange={event => setConditions(event.target.value)} maxLength={10000} rows={3} placeholder="例如：不改变现有设备数量"/></Field></div>
        </details>

      </fieldset>
      {busy && <section className="pd-upload-progress" role="status" aria-live="polite" aria-busy="true"><span className="pd-spinner"/><div><strong>{progress}</strong><progress className="pd-native-progress" max={uploadProgress.total || 1} value={uploadProgress.completed} aria-label="资料上传解析进度" aria-valuetext={`${uploadProgress.completed} / ${uploadProgress.total} 份资料已完成`}/><p>已完成 {uploadProgress.completed} / {uploadProgress.total} 份资料</p></div></section>}
      <div className="pd-form-footer"><span role="status" aria-live="polite">{busy ? '资料提交后自动打开节点进度。' : "蓝图需本人确认，再编制三类成果。"}</span><div className="pd-actions">{createdId && !busy && <button type="button" className="button secondary" onClick={() => leave(createdId)}>查看项目进度</button>}<button className="button primary" disabled={busy}>{busy ? "正在提交…" : pending ? "重试并继续" : canGenerate ? "开始生成" : "上传并保存资料"}<ProductIcon name="arrow"/></button></div></div>
    </form>
    <aside className="pd-new-aside"><section className="pd-panel"><h3>本次交付</h3><ul><li><ProductIcon name="file"/>技术方案 · DOCX<small>正文 ≥ 50,000 字 · 图表 ≥ 15 张</small></li><li><ProductIcon name="file"/>可行性研究报告 · DOCX<small>正文 ≥ 70,000 字 · 图表 ≥ 20 张</small></li><li><ProductIcon name="layers"/>汇报演示文稿 · PPTX<small>基于两份报告编制，共用事实来源</small></li></ul><p className="pd-muted">创建后显示真实成果状态与版本。</p><div className="pd-intake-steps"><h3>一起推进项目</h3><ol><li>解析背景与设备清单</li><li>检索知识并生成蓝图</li><li>本人确认蓝图</li><li>编制正文、图表与汇报文稿</li><li>下载三件套成果</li></ol></div></section>{!data.capabilities.retrieval && <section className="pd-service-note" role="note"><ProductIcon name="shield"/><p>知识库未启用；生成能否继续以后台实际状态为准。</p></section>}{!canGenerate && <section className="pd-service-note"><ProductIcon name="shield"/><p>生成授权未开通，资料仍可保存。</p></section>}</aside></div>
  </div>;
}
