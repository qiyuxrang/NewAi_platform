/* 成本测算台 —— 前端逻辑。无框架、无外网依赖。 */
(() => {
  const $ = (s) => document.querySelector(s);

  /* ── 取价链：六级，顺序就是引擎真实的取价顺序 ───────────── */
  const RUNGS = [
    { no: "01", name: "企业价格库",     key: ["企业价格库"],           kind: "hit" },
    { no: "02", name: "历史报价库",     key: ["企业历史报价库"],        kind: "hit" },
    { no: "03", name: "规格公式",       key: ["电缆行情公式"],          kind: "hit",
      fuse: ["钢管规格公式", "电缆行情公式"] },
    { no: "04", name: "互联网检索",     key: ["互联网检索"],            kind: "hit" },
    { no: "05", name: "含量库 / 人工",  key: ["人工含量库", "人工含量"], kind: "hit" },
    { no: "06", name: "经验暂估",       key: ["品类经验暂估", "保守暂估", "暂估"],
      kind: "est", note: "必须询价" },
  ];

  const ladderList = $("#ladderList");
  ladderList.innerHTML = RUNGS.map((r, i) => `
    <li data-i="${i}">
      <span class="rung-no">${r.no}</span>
      <span class="rung-name">${r.name}</span>
      <span class="rung-track"><span class="rung-fill"></span></span>
      <span class="rung-num">—</span>
    </li>`).join("");

  function ladderIdle() {
    ladderList.querySelectorAll("li").forEach((li, i) => {
      li.className = "";
      li.querySelector(".rung-fill").style.width = "0%";
      li.querySelector(".rung-num").textContent = "—";
      // 载入时让阶梯依次亮一下，交代"这是取价顺序"
      setTimeout(() => {
        li.classList.add(i < 4 ? "hit" : "est");
        li.querySelector(".rung-fill").style.width = "14%";
        setTimeout(() => {
          li.classList.remove("hit", "est");
          li.querySelector(".rung-fill").style.width = "0%";
        }, 520);
      }, 300 + i * 110);
    });
    $("#ladderHint").textContent = "跑完显示每一层实际命中多少条";
  }

  function ladderRunning() {
    ladderList.querySelectorAll("li").forEach((li) => {
      li.className = "";
      li.querySelector(".rung-fill").style.width = "0%";
      li.querySelector(".rung-num").textContent = "…";
    });
    $("#ladderHint").textContent = "正在按顺序取价…";
    // 引擎内部顺序不可见，这里给一个"从上往下走"的示意，不假装精确
    let i = 0;
    ladderRunning.timer = setInterval(() => {
      ladderList.querySelectorAll("li").forEach((li, k) => {
        if (k < i && !li.classList.contains("hit")) {
          li.classList.add(k < 5 ? "hit" : "est");
          li.querySelector(".rung-fill").style.width = "22%";
        }
      });
      const cur = ladderList.querySelector(`li[data-i="${i}"]`);
      if (cur) cur.classList.add("active");
      const prev = ladderList.querySelector(`li[data-i="${i - 1}"]`);
      if (prev) prev.classList.remove("active");
      i = (i + 1) % 6;
    }, 900);
  }

  function ladderResult(dist, total) {
    clearInterval(ladderRunning.timer);
    const totalN = Math.max(1, total || 1);
    let estN = 0;
    RUNGS.forEach((r, i) => {
      const li = ladderList.querySelector(`li[data-i="${i}"]`);
      li.className = "";
      const n = (r.key || []).reduce((s, k) => s + (dist[k] || 0), 0);
      const pct = Math.min(100, Math.round((n / totalN) * 100));
      li.querySelector(".rung-fill").style.width = pct + "%";
      li.querySelector(".rung-num").textContent = n ? n + " 项" : "0";
      if (n) li.classList.add(r.kind);
      if (r.kind === "est") estN += n;
    });
    $("#ladderHint").textContent = estN
      ? `${estN} 项走经验暂估，须询价`
      : "全部落在有据可查的层级";
    return estN;
  }

  /* ── 提交与轮询 ─────────────────────────────────────────── */
  const form = $("#form"), runBtn = $("#run"), err = $("#err");
  const runState = $("#runState"), runStep = $("#runStep"), runClock = $("#runClock");
  let clockTimer = null, pollTimer = null, t0 = 0;

  const fmt = (n, d = 2) =>
    (n === null || n === undefined || n === "") ? "—"
      : Number(n).toLocaleString("zh-CN", { minimumFractionDigits: d, maximumFractionDigits: d });

  const wan = (v) => (v || v === 0) ? fmt(Number(v) / 10000, 2) + " 万" : "—";

  function bindDrop(inputSel, dropSel, nameSel) {
    const input = $(inputSel), drop = $(dropSel), tag = $(nameSel);
    const show = () => {
      if (input.files && input.files[0]) {
        tag.hidden = false;
        tag.textContent = input.files[0].name;
        drop.classList.add("has");
      }
    };
    input.addEventListener("change", show);
    ["dragenter", "dragover"].forEach((e) =>
      drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach((e) =>
      drop.addEventListener(e, () => drop.classList.remove("over")));
    drop.addEventListener("drop", (ev) => {
      ev.preventDefault();
      if (ev.dataTransfer.files.length) {
        input.files = ev.dataTransfer.files;
        show();
      }
    });
  }
  bindDrop("#boq", "#dropBoq", "#boqName");
  bindDrop("#bg", "#dropBg", "#bgName");

  function setRunning(on) {
    runBtn.disabled = on;
    runBtn.querySelector(".btn-label").textContent = on ? "正在测算" : "开始测算";
    runState.hidden = !on;
    if (on) {
      t0 = Date.now();
      runClock.textContent = "0:00";
      clockTimer = setInterval(() => {
        const s = Math.floor((Date.now() - t0) / 1000);
        runClock.textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
      }, 500);
    } else {
      clearInterval(clockTimer);
    }
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    err.hidden = true;
    const boq = $("#boq").files[0];
    if (!boq) { err.hidden = false; err.textContent = "先选一份清单（xlsx）。"; return; }
    const fd = new FormData();
    fd.append("file", boq);
    if ($("#bg").files[0]) fd.append("bg_file", $("#bg").files[0]);
    fd.append("note", $("#note").value || "");
    fd.append("region", "陕西");

    setRunning(true);
    ladderRunning();
    try {
      const r = await fetch("/api/jobs", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || "提交失败");
      if (j.模式 === "入库") {
        setRunning(false);
        clearInterval(ladderRunning.timer);
        ladderIdle();
        $("#footMsg").textContent = "已入库：" + JSON.stringify(j.入库报告 || {}).slice(0, 90);
        return;
      }
      poll(j.job_id);
    } catch (e) {
      fail(e.message);
    }
  });

  function fail(msg) {
    setRunning(false);
    clearInterval(ladderRunning.timer);
    ladderIdle();
    ladderList.querySelectorAll("li").forEach((li) => (li.className = ""));
    err.hidden = false;
    err.textContent = msg;
  }

  function poll(id) {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(async () => {
      let job;
      try {
        const r = await fetch("/api/jobs/" + id);
        job = await r.json();
        if (!r.ok) throw new Error(job.detail || "查询失败");
      } catch (e) { fail("查询任务失败：" + e.message); return; }

      if (job.step) runStep.textContent = job.step;
      if (job.status === "queued" || job.status === "running") { poll(id); return; }
      if (job.status === "error") {
        fail("这份清单没跑通：" + (job.error || "未知错误") +
             "。检查表头是不是「项目名称 / 数量 / 单位」这几列；也可能是文件被 Excel 占着。");
        return;
      }
      clearInterval(ladderRunning.timer);
      setRunning(false);
      render(job);
    }, 1500);
  }

  /* ── 渲染结果 ───────────────────────────────────────────── */
  let lastJobId = "";

  function render(job) {
    const d = job.result || {};
    lastJobId = job.id;
    const hc = d["取价健康度"] || {};
    const dist = hc["来源分布"] || {};
    const estN = ladderResult(dist, hc["行数"]);

    $("#resTitle").textContent = d["项目名称"] || job["清单文件名"] || "测算结果";
    const chk = d["校验"] || {};
    $("#resSub").textContent = [
      job["清单文件名"],
      "耗时 " + (job["耗时_seconds"] || "—") + " 秒",
      "通用校验 " + (chk["通过数"] || "—") + "/" + (chk["总检查"] || "—") + " 项通过",
      d["地区"] ? "地区 " + d["地区"] : "",
    ].filter(Boolean).join(" · ");

    /* 关键数字 */
    const a = d["甲供C30版"] || {}, b = d["不提供C30版"] || {}, net = d["纯网报价"] || {};
    const own = d["供应归属清点"] || {};
    const ownTxt = Object.entries(own).map(([k, v]) => `${k} ${v}`).join(" · ") || "—";
    const kpis = [
      { cls: "key", label: "成本测算总计（含税）", value: wan(a["总计"]),
        note: `直接费 ${wan(a["直接费"])}，取费 ${wan(a["取费"])}` },
      { label: d["纯采购清单"] ? "设备材料采购总包（含税）" : "劳务报价（对外总包·含税）",
        value: wan(d["劳务报价总包"]),
        note: d["纯采购清单"] ? "设备材料 + 采购管理费 5% + 税 3%" : "劳务分包口径，不含甲供设备材料" },
      { label: "纯网络检索口径", value: wan(net["总计"]),
        note: net["每单位"] ? `折合 ${fmt(net["每单位"])} 元/单位` : "全部走互联网检索" },
      { cls: estN ? "warn" : "", label: "取价命中率", value: fmt((hc["命中率"] || 0) * 100, 0) + "%",
        note: `${hc["行数"] || 0} 行里 ${hc["零价项"] || 0} 行无价；${estN} 项经验暂估` },
      { label: "供应归属", value: `${Object.values(own).reduce((s, v) => s + v, 0)} 项`, note: ownTxt },
    ];
    $("#kpis").innerHTML = kpis.map((k) => `
      <div class="kpi ${k.cls || ""}">
        <p class="k-label">${k.label}</p>
        <p class="k-value">${k.value}</p>
        <p class="k-note">${k.note}</p>
      </div>`).join("");

    /* 六张表 */
    const six = [
      ["①", "设备清单", "逐行标采购方式 / 报价口径 + 来源 + 链接 + 可信度"],
      ["②", "劳务清单", "按施工分类，只计人工与机械"],
      ["③", "成本测算（库+网检索）", "价格库 → 历史价 → 公式 → 互联网"],
      ["④", "成本测算（纯网检索）", "全部走互联网检索，用于比价"],
      ["⑤", "劳务报价（库+网检索）", d["纯采购清单"] ? "设备材料采购总包报价" : "对外总包报价，含取费链"],
      ["⑥", "劳务报价（纯网检索）", d["纯采购清单"] ? "设备材料采购总包报价" : "人工单价走网查口径"],
    ].map(([no, name, meta]) => `
      <li><span class="s-no">${no}</span><span class="s-name">${name}</span>
      <span class="s-meta">${meta}</span></li>`).join("");
    $("#sheetList").innerHTML = six;

    /* 交付说明 */
    $("#report").innerHTML = md(d["报告"] || "（引擎没有返回交付说明）");

    /* 下载与路径 */
    const dl = $("#dl");
    dl.href = "/api/jobs/" + job.id + "/download";
    dl.setAttribute("download", "");
    $("#deliverPath").textContent = "同时已导出到：" + (d["导出目录"] || "—");
    $("#hostPath").textContent = (d["导出目录"] || $("#hostPath").textContent) + "\\";
    $("#footMsg").textContent = "文件已生成，可直接打开 Excel 复核";

    const res = $("#result");
    res.hidden = false;
    res.scrollIntoView({ behavior: "smooth", block: "start" });
    loadRecent();
  }

  /* 极简 markdown：标题 / 粗体 / 列表 / 代码 / 分隔线 */
  function md(s) {
    const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const inline = (t) => esc(t)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
    const out = [];
    let list = false;
    for (const raw of String(s).split(/\r?\n/)) {
      const line = raw.trimEnd();
      const li = line.match(/^\s*[-*]\s+(.*)$/);
      if (li) {
        if (!list) { out.push("<ul>"); list = true; }
        out.push("<li>" + inline(li[1]) + "</li>");
        continue;
      }
      if (list) { out.push("</ul>"); list = false; }
      if (!line.trim()) continue;
      if (/^###\s+/.test(line)) out.push("<h3>" + inline(line.replace(/^###\s+/, "")) + "</h3>");
      else if (/^##\s+/.test(line)) out.push("<h2>" + inline(line.replace(/^##\s+/, "")) + "</h2>");
      else if (/^#\s+/.test(line)) out.push("<h1>" + inline(line.replace(/^#\s+/, "")) + "</h1>");
      else if (/^---+$/.test(line)) out.push("<hr>");
      else out.push("<p>" + inline(line) + "</p>");
    }
    if (list) out.push("</ul>");
    return out.join("");
  }

  /* ── 侧栏数据 ───────────────────────────────────────────── */
  async function loadLibrary() {
    try {
      const r = await fetch("/api/library");
      const j = await r.json();
      $("#s1").textContent = fmt(j["材料库"], 0) + " 条";
      $("#s2").textContent = fmt(j["历史报价"], 0) + " 条";
      $("#s3").textContent = fmt(j["网价入库"], 0) + " 条";
      $("#libTotal").textContent = fmt(j["合计"], 0);
    } catch (e) { /* 首屏拿不到不影响使用 */ }
  }

  async function loadRecent() {
    try {
      const r = await fetch("/api/recent");
      const j = await r.json();
      const list = j["最近"] || [];
      $("#recent").innerHTML = list.length ? list.map((x) => `
        <li><span class="r-name">${x["项目"] || "（未命名）"}</span>
        <span class="r-meta">${wan(x["总计"])} · ${x["秒"] || "—"}s</span></li>`).join("")
        : '<li class="empty">还没有记录。</li>';
    } catch (e) { /* 忽略 */ }
  }

  $("#again").addEventListener("click", () => {
    $("#result").hidden = true;
    form.reset();
    $("#boqName").hidden = $("#bgName").hidden = true;
    ladderIdle();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  $("#copyPath").addEventListener("click", async () => {
    const t = $("#hostPath").textContent;
    try {
      await navigator.clipboard.writeText(t);
      $("#copyPath").textContent = "已复制";
      setTimeout(() => ($("#copyPath").textContent = "复制路径"), 1400);
    } catch (e) {
      $("#copyPath").textContent = "复制失败，手动选一下";
    }
  });

  /* ── 启动 ───────────────────────────────────────────────── */
  $("#today").textContent = new Date().toLocaleDateString("zh-CN").replace(/\//g, "-");
  ladderIdle();
  loadLibrary();
  loadRecent();
})();
