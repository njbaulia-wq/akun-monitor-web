/* PantauAkun — SPA logic (vanilla JS, no framework). */
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const fmt = (n) => (n === null || n === undefined) ? "–" : Number(n).toLocaleString("id-ID");
const PLAT = { tiktok: "TikTok", instagram: "Instagram", threads: "Threads", facebook: "Facebook" };

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), 3200);
}
function badge(p) {
  return `<span class="badge ${p || "unknown"}">${PLAT[p] || "?"}</span>`;
}
function weekRange() {
  return { sejak: $("#sejak").value, sampai: $("#sampai").value };
}
function defaultWeek() {
  const now = new Date();
  const day = (now.getDay() + 6) % 7; // Senin=0
  const mon = new Date(now); mon.setDate(now.getDate() - day);
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6);
  const f = (d) => d.toISOString().slice(0, 10);
  $("#sejak").value = f(mon); $("#sampai").value = f(sun);
}

/* ---------- nav ---------- */
$$(".nav-btn").forEach((b) =>
  b.addEventListener("click", () => {
    $$(".nav-btn").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $$(".view").forEach((v) => v.classList.remove("active"));
    $("#view-" + b.dataset.view).classList.add("active");
    if (b.dataset.view === "dashboard") loadDashboard();
    if (b.dataset.view === "akun") loadAkun();
    if (b.dataset.view === "follow") loadFollow();
    if (b.dataset.view === "pengaturan") loadSettings();
    if (b.dataset.view === "data") loadDataStat();
    closeNav();
  })
);

/* ---------- navigasi mobile (drawer) ----------
   Di layar < 900px sidebar jadi drawer yang muncul lewat tombol ☰.
   Versi lama menyembunyikan sidebar sepenuhnya tanpa alternatif, jadi
   aplikasi tidak bisa dipakai di HP sama sekali. */
function navOpen() { return document.body.classList.contains("nav-open"); }
function openNav() {
  document.body.classList.add("nav-open");
  $("#navBackdrop").hidden = false;
  $("#navToggle").setAttribute("aria-expanded", "true");
}
function closeNav() {
  document.body.classList.remove("nav-open");
  $("#navBackdrop").hidden = true;
  $("#navToggle").setAttribute("aria-expanded", "false");
}
function toggleNav() { navOpen() ? closeNav() : openNav(); }

$("#navToggle")?.addEventListener("click", toggleNav);
$("#navBackdrop")?.addEventListener("click", closeNav);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && navOpen()) closeNav();
});
// Memilih halaman di drawer tidak boleh menutupnya di layar lebar
let _mm = null;
window.addEventListener("resize", () => {
  const mobile = window.matchMedia("(max-width: 900px)").matches;
  if (!mobile && navOpen()) closeNav();
  if (_mm !== mobile) { _mm = mobile; closeNav(); }
});

/* ---------- dashboard ---------- */
let DASH = { rows: [], sortKey: "interaksi", sortDir: -1 };

// Angka "—" (null) selalu di paling bawah, apa pun arah urutan.
function cmpNum(a, b) {
  const av = a == null ? -Infinity : a;
  const bv = b == null ? -Infinity : b;
  return av === bv ? 0 : (av < bv ? -1 : 1);
}
function sortRows(rows) {
  const k = DASH.sortKey, dir = DASH.sortDir;
  return [...rows].sort((x, y) => {
    let d;
    if (k === "username" || k === "platform")
      d = String(x[k] || "").localeCompare(String(y[k] || ""), "id");
    else if (k === "kode")
      d = String(x[k] || "").localeCompare(String(y[k] || ""), "id", { numeric: true });
    else
      d = cmpNum(x[k], y[k]);
    return d * dir;
  });
}
function deltaHtml(now, prev) {
  if (now == null || prev == null) return "";
  const d = now - prev;
  if (!d) return `<span class="dlt flat">→ sama</span>`;
  const pct = prev ? Math.round((d / prev) * 100) : null;
  return `<span class="dlt ${d > 0 ? "up" : "down"}">` +
    `${d > 0 ? "▲" : "▼"} ${fmt(Math.abs(d))}` +
    (pct === null ? "" : ` (${pct > 0 ? "+" : ""}${pct}%)`) + `</span>`;
}

async function loadDashboard() {
  const { sejak, sampai } = weekRange();
  const plat = $("#filterPlatform").value;
  const q = new URLSearchParams({ sejak, sampai, ...(plat ? { platform: plat } : {}) });
  const { rows } = await api("/api/dashboard?" + q);
  DASH.rows = rows;

  const term = ($("#cari").value || "").toLowerCase();
  const list = sortRows(rows.filter(
    (r) => !term || r.username.toLowerCase().includes(term) || String(r.kode || "").includes(term)
  ));
  const tb = $("#tblDash tbody");
  tb.innerHTML = list.map((r) => `
    <tr>
      <td>${r.kode ?? ""}</td><td>${badge(r.platform)}</td>
      <td><b>${esc(r.username)}</b></td>
      <td class="num">${fmt(r.views)}</td><td class="num">${fmt(r.komen)}</td>
      <td class="num">${fmt(r.share)}</td><td class="num">${fmt(r.like)}</td>
      <td class="num">${fmt(r.repost)}</td><td class="num"><b>${fmt(r.interaksi)}</b></td>
      <td class="num">${r.n_post}</td>
      <td><button class="btn ghost" data-det="${r.account_id}">detail</button></td>
    </tr>`).join("");
  $("#dashEmpty").hidden = rows.length > 0;
  tb.querySelectorAll("[data-det]").forEach((b) =>
    b.addEventListener("click", () => showDetail(+b.dataset.det))
  );

  // stats + perbandingan dengan periode sebelumnya (selama durasi yang sama)
  const tot = (k) => rows.reduce((s, r) => s + (r[k] || 0), 0);
  $("#stats").innerHTML = [
    ["Interaksi total", fmt(tot("interaksi")), DASH.prev?.interaksi],
    ["Postingan", fmt(tot("n_post")), DASH.prev?.posts],
    ["Akun aktif", rows.filter((r) => r.n_post > 0).length + " / " + rows.length, null],
    ["Like", fmt(tot("like")), DASH.prev?.like],
  ].map(([k, v, prev]) =>
    `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div>` +
    `<div class="d">${prev === undefined || prev === null ? "" :
        "vs periode sebelumnya " + deltaHtml(
          k === "Postingan" ? tot("n_post") : (k === "Like" ? tot("like") : tot("interaksi")),
          prev)}</div></div>`).join("");
  updateCounts();
  renderSpark();
}

/* ---------- bandingkan dengan periode sebelumnya ---------- */
async function loadPrev() {
  const { sejak, sampai } = weekRange();
  const plat = $("#filterPlatform").value;
  const d1 = new Date(sejak), d2 = new Date(sampai);
  const hari = Math.round((d2 - d1) / 86400000) + 1;
  const p2 = new Date(d1); p2.setDate(p2.getDate() - 1);
  const p1 = new Date(p2); p1.setDate(p1.getDate() - hari + 1);
  const f = (x) => x.toISOString().slice(0, 10);
  const btn = $("#btnBanding");
  btn.disabled = true;
  try {
    const q = new URLSearchParams({
      sejak: f(p1), sampai: f(p2), ...(plat ? { platform: plat } : {}) });
    const { rows } = await api("/api/dashboard?" + q);
    const tot = (k) => rows.reduce((s, r) => s + (r[k] || 0), 0);
    DASH.prev = { interaksi: tot("interaksi"), posts: tot("n_post"), like: tot("like") };
    DASH.prevLabel = `${f(p1)} s.d. ${f(p2)}`;
    $("#prevInfo").textContent =
      `Membandingkan dengan ${DASH.prevLabel} (${hari} hari sebelum).`;
    $("#prevInfo").hidden = false;
  } catch {
    $("#prevInfo").textContent = "Gagal memuat periode sebelumnya.";
    $("#prevInfo").hidden = false;
  } finally {
    btn.disabled = false;
    loadDashboard();
  }
}

/* ---------- sparkline tren (SVG, tanpa library) ---------- */
function renderSpark() {
  const box = $("#trenBox");
  if (!box) return;
  const { sejak, sampai } = weekRange();
  api(`/api/trend?sejak=${sejak}&sampai=${sampai}`).then((t) => {
    const pts = t.points || [];
    if (pts.length < 2) { box.hidden = true; return; }
    box.hidden = false;
    const w = 640, h = 90, pad = 4;
    const max = Math.max(1, ...pts.map((p) => p.interaksi));
    const dx = (w - pad * 2) / (pts.length - 1);
    const y = (v) => h - pad - (v / max) * (h - pad * 2);
    const d = pts.map((p, i) =>
      `${i ? "L" : "M"}${(pad + i * dx).toFixed(1)},${y(p.interaksi).toFixed(1)}`).join("");
    const area = `${d}L${(pad + (pts.length - 1) * dx).toFixed(1)},${h - pad}` +
                `L${pad},${h - pad}Z`;
    $("#trenSvg").innerHTML = `
      <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img"
           aria-label="Tren interaksi harian">
        <path d="${area}" fill="rgba(38,198,160,.14)"/>
        <path d="${d}" fill="none" stroke="#26c6a0" stroke-width="2"
              vector-effect="non-scaling-stroke"/>
      </svg>
      <div class="tren-ax">
        <span>${esc(pts[0].hari)}</span>
        <span>total ${fmt(pts.reduce((s, p) => s + p.interaksi, 0))}</span>
        <span>${esc(pts[pts.length - 1].hari)}</span>
      </div>`;
  }).catch(() => { box.hidden = true; });
}
$("#btnBanding")?.addEventListener("click", loadPrev);

// tombol "Buka Pengaturan" di kotak peringatan sesi login
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-goto]");
  if (!t) return;
  e.preventDefault();
  const btn = $$(".nav-btn").find((b) => b.dataset.view === t.dataset.goto);
  btn?.click();
});

/* ---------- sorting kolom ---------- */
(function () {
  const COLS = {
    kode: "Kode", platform: "Platform", username: "Username",
    views: "Views", komen: "Komen", share: "Share", like: "Like",
    repost: "Repost", interaksi: "Interaksi", n_post: "Post",
  };
  const thead = $("#tblDash thead tr");
  if (!thead) return;
  const cells = [...thead.querySelectorAll("th")];
  cells.forEach((th, i) => {
    const key = Object.keys(COLS)[i];
    if (!key) return;
    th.classList.add("sortable");
    th.setAttribute("role", "button");
    th.setAttribute("tabindex", "0");
    th.title = "Klik untuk urutkan";
    th.addEventListener("click", () => {
      if (DASH.sortKey === key) DASH.sortDir *= -1;
      else { DASH.sortKey = key; DASH.sortDir = -1; }
      renderSortMarks();
      loadDashboard();
    });
    th.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); th.click(); }
    });
  });
})();

function renderSortMarks() {
  const keys = Object.keys(
    { kode: 1, platform: 1, username: 1, views: 1, komen: 1, share: 1,
      like: 1, repost: 1, interaksi: 1, n_post: 1 });
  document.querySelectorAll("#tblDash thead th").forEach((th, i) => {
    const on = keys[i] === DASH.sortKey;
    th.classList.toggle("sorted", on);
    th.setAttribute("aria-sort",
      on ? (DASH.sortDir === -1 ? "descending" : "ascending") : "none");
    th.dataset.mark = on ? (DASH.sortDir === -1 ? " ▼" : " ▲") : "";
  });
}
async function updateCounts() {
  const c = await api("/api/counts").catch(() => ({}));
  $("#sideCounts").innerHTML = Object.entries(PLAT)
    .map(([k, v]) => `<div><span>${v}</span><b>${c[k] || 0}</b></div>`)
    .join("");
}
async function showDetail(accId) {
  const { sejak, sampai } = weekRange();
  const posts = await api(`/api/account/${accId}/posts?sejak=${sejak}&sampai=${sampai}`);
  const accs = await api("/api/accounts");
  const a = accs.find((x) => x.id === accId) || {};
  $("#detailTitle").textContent = `@${a.username} — ${PLAT[a.platform] || ""} (${posts.length} postingan)`;
  $("#tblPosts tbody").innerHTML = posts.map((p) => {
    const m = p.metrics || {};
    return `<tr><td>${(p.posted_at || "").slice(0, 10)}</td>
      <td class="linkcell"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.url.slice(0, 48))}…</a></td>
      <td class="num">${fmt(m.views)}</td><td class="num">${fmt(m.like)}</td>
      <td class="num">${fmt(m.komen)}</td><td class="num">${fmt(m.share)}</td>
      <td class="num">${fmt(m.repost)}</td>
      <td><button class="btn ghost" data-hist="${p.id}">riwayat</button>
      <button class="btn ghost" data-delpost="${p.id}">✕</button></td></tr>`;
  }).join("");
  curAccId = accId;
  $$("#tblPosts [data-hist]").forEach((b) =>
    b.addEventListener("click", () => showPostHistory(+b.dataset.hist)));
  $$("#tblPosts [data-delpost]").forEach((b) =>
    b.addEventListener("click", async () => {
      if (!confirm("Hapus Posting ini beserta seluruh riwayat metriknya?")) return;
      const r = await api("/api/posts/" + b.dataset.delpost, { method: "DELETE" });
      toast(`Dihapus: ${r.posts} postingan, ${r.metrics} metrik.`);
      showDetail(curAccId);
    }));
  $("#detailAkun").hidden = false;
  $("#detailAkun").scrollIntoView({ behavior: "smooth" });
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- input link (background job) ---------- */
let JOB = null;      // {id, items:[...]}
let JOB_TIMER = null;
// Halaman hasil: untuk 1000 link, merender semua baris menghasilkan 6,3 MB
// HTML + 223.000 elemen <option> -> browser membeku. Hanya sebagian baris
// dirender per halaman; JOB.items tetap lengkap untuk Simpan & Ulangi.
const PAGE_SIZE = 100;
let HAL = 1;
let ACC_CACHE = [];

function jobItemData(it) {
  // samakan bentuk dgn endpoint /api/links/save (_data)
  return it.data;
}

$("#taLinks").addEventListener("input", () => {
  const n = $("#taLinks").value.split("\n").map((s) => s.trim()).filter(Boolean).length;
  $("#prosesInfo").textContent = n ? `${n} link` : "";
});

// linkcell: teks link yg bisa diklik
function linkCell(url, maxlen = 40) {
  const short = esc(url.length > maxlen ? url.slice(0, maxlen) + "…" : url);
  return `<span class="linkcell" title="${esc(url)}"><a href="${esc(url)}" target="_blank" rel="noopener">${short}</a></span>`;
}

$("#btnImportLinks").addEventListener("click", async () => {
  const f = $("#fileLinks").files[0];
  if (!f) return toast("Pilih dulu file (.xlsx atau .csv) yang berisi link.");
  const fd = new FormData();
  fd.append("file", f);
  const btn = $("#btnImportLinks");
  btn.disabled = true;
  try {
    const r = await fetch("/api/links/import-excel", { method: "POST", body: fd });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !r.headers.get("Content-Type")?.includes("application/json"))
      throw new Error(j.error || ("HTTP " + r.status));
    if (!j.links.length) {
      toast("Tidak ada link postingan terdeteksi di file itu." +
        (j.dilewati_profil ? ` ${j.dilewati_profil} link profil dilewati.`
          + (j.dilewati_facebook ? ` ${j.dilewati_facebook} link profil/grup Facebook.` : "") : ""));
      return;
    }
    const ada = new Set($("#taLinks").value.split("\n").map((s) => s.trim()).filter(Boolean));
    const baru = j.links.filter((u) => !ada.has(u));
    const cur = $("#taLinks").value.trim();
    $("#taLinks").value = (cur ? cur + "\n" : "") + baru.join("\n");
    $("#taLinks").dispatchEvent(new Event("input"));
    const pp = j.per_platform || {};
    const rinc = ["tiktok", "instagram", "threads", "facebook"].filter((k) => pp[k])
      .map((k) => `${PLAT[k]}: ${pp[k]}`).join(", ");
    let msg = `${baru.length} link baru ditambahkan (${rinc || "campuran"}).`;
    if (j.dilewati_profil) msg += ` ${j.dilewati_profil} link profil dilewati.`;
    if (j.dilewati_facebook)
      msg += ` ${j.dilewati_facebook} link profil/grup Facebook dilewati (bukan postingan).`;
    toast(msg);
  } catch (e) {
    toast("Gagal: " + e.message);
  } finally {
    btn.disabled = false;
    $("#fileLinks").value = "";
  }
});

$("#btnProses").addEventListener("click", async () => {
  const urls = $("#taLinks").value.split("\n").map((s) => s.trim()).filter(Boolean);
  if (!urls.length) return toast("Tempel dulu link postingannya.");
  const btn = $("#btnProses");
  btn.disabled = true;
  try {
    const r = await api("/api/links/scrape-job", {
      method: "POST", body: JSON.stringify({ urls }),
    });
    ACC_CACHE = await api("/api/accounts");
    clearOptCache();
    JOB = { id: r.job_id, items: [] };
    HAL = 1;
    $("#hasilCard").hidden = false;
    $("#jobProg").hidden = false;
    $("#btnSimpan").disabled = true;
    $("#btnRetry").hidden = true;
    const dup = r.dimasukkan - r.total;
    toast(`Mulai scrape ${r.total} link unik.` + (dup ? ` ${dup} duplikat dibuang.` : ""));
    pollJob();
  } catch (e) {
    toast("Gagal: " + e.message);
  } finally {
    btn.disabled = false;
  }
});

/* PollING RINGAN: hanya counter, tanpa daftar item.
   Untuk 1000 link, payload penuh = 623 KB tiap polling (~1,8 GB selama
   100 menit). Ringkas = ~0,1 KB. Render penuh cukup saat poll terakhir. */
async function pollJob() {
  clearTimeout(JOB_TIMER);
  if (!JOB) return;
  const done = await api("/api/jobs/" + JOB.id + "?lite=1").catch(() => null);
  if (!done) return;
  JOB = Object.assign(JOB, done);
  const pct = done.total ? Math.round((100 * done.done) / done.total) : 0;
  $("#jobBar").style.width = pct + "%";
  $("#jobTxt").textContent = `${done.done}/${done.total} — ok ${done.ok}, gagal ${done.fail}`;
  if (done.status !== "done") {
    JOB_TIMER = setTimeout(pollJob, 2000);
    return;
  }
  // selesai -> ambil daftar lengkap SEKALI untuk render
  const full = await api("/api/jobs/" + JOB.id).catch(() => null);
  if (full) {
    JOB.items = full.items || [];
    renderJobItems(JOB.items);
  }
  $("#jobProg").hidden = true;
  $("#btnSimpan").disabled = false;
  // Sesi login mati di tengah batch -> beri tahu, jangan biarkan user
  // mengira link-nya memang rusak.
  if (done.auth_stopped) {
    $("#authWarn").hidden = false;
    $("#authWarnTxt").textContent =
      `Sesi login ${done.auth_stopped} tidak valid (cookie habis/ kedaluwarsa). ` +
      `Link ${done.auth_stopped} yang tersisa DILEWATI, bukan gagal scraping. ` +
      `Isi ulang cookie di Pengaturan, lalu klik "Ulangi yang gagal".`;
  } else {
    $("#authWarn").hidden = true;
  }
  const retryable = JOB.items.filter((it) => it.status === "failed" && it.retryable).length;
  $("#btnRetry").hidden = retryable === 0;
  if (retryable) $("#btnRetry").textContent = `↻ Ulangi yang gagal (${retryable})`;
}

$("#btnRetry").addEventListener("click", async () => {
  if (!JOB) return;
  const r = await api(`/api/links/job/${JOB.id}/retry`, { method: "POST" });
  if (!r.retried) return toast("Tidak ada yang bisa diulang.");
  toast(`Mengulang ${r.retried} link…`);
  $("#jobProg").hidden = false;
  $("#btnRetry").hidden = true;
  $("#btnSimpan").disabled = true;
  pollJob();
});

function statusCell(it) {
  if (it.status === "pending") return `<span class="muted">⏳ antre</span>`;
  if (it.status === "running") return `<span class="muted">🔄 scraping…</span>`;
  if (it.status === "failed")
    return `<span class="st err">gagal: ${esc(it.error || "")}</span>` +
      (it.retryable ? ` <span class="st warn">(bisa diulang)</span>` : "");
  const m = it.matched_account;
  if (it.already_saved) return `<span class="st warn">sudah tersimpan</span>`;
  return m ? `<span class="st ok">✓ cocok otomatis</span>` : `<span class="st warn">pilih manual</span>`;
}

/* Cache <option> per platform. Versi lama membangun ulang daftar akun
   untuk SETIAP baris: 223 akun x 1000 baris = 223.000 elemen <option>
   tiap render. Dengan cache: 223 elemen. */
let _OPT_CACHE = {};
function optCache(platform) {
  if (!_OPT_CACHE[platform])
    _OPT_CACHE[platform] = ACC_CACHE.filter((a) => a.platform === platform)
      .map((a) => `<option value="${a.id}">${esc(a.kode || "")} @${esc(a.username)}</option>`)
      .join("");
  return _OPT_CACHE[platform];
}
function clearOptCache() { _OPT_CACHE = {}; }

/* ---------- audit: verifikasi tanggal ---------- */
const AUDIT_META = {
  ok: { icon: "✅", label: "Terverifikasi",
        title: "Tanggal dari timestamp asli platform (jam & menit tepat)" },
  wajar: { icon: "⚠️", label: "Tingkat hari",
           title: "Platform hanya memberi tanggal, tanpa jam. Jam 00:00 adalah placeholder, bukan waktu unggah sebenarnya." },
  periksa: { icon: "❌", label: "Periksa",
             title: "Ada yang janggal pada tanggal atau data posting ini" },
};

function auditCell(it) {
  if (it.status !== "ok") return `<span class="muted">—</span>`;
  const a = it.audit || { level: "ok", flags: [], catatan: "" };
  const m = AUDIT_META[a.level] || AUDIT_META.ok;
  const flags = (a.flags || []).length
    ? `<div class="muted small">${esc(a.flags.join(", "))}</div>` : "";
  return `<span class="abadge ${a.level}" title="${esc(a.catatan || m.title)}">
    ${m.icon} ${m.label}</span>${flags}`;
}

function renderAuditBox(items) {
  const box = $("#auditBox");
  if (!box) return;
  const ok = items.filter((i) => (i.audit || {}).level === "ok").length;
  const wajar = items.filter((i) => (i.audit || {}).level === "wajar").length;
  const periksa = items.filter((i) => (i.audit || {}).level === "periksa").length;
  const total = ok + wajar + periksa;
  if (!total) { box.hidden = true; return; }
  box.hidden = false;
  box.innerHTML = `
    <b>🔎 Audit data (${total} link berhasil di-scrape)</b>
    <span class="abadge ok">✅ ${ok} tanggal terverifikasi</span>
    <span class="abadge wajar">⚠️ ${wajar} hanya tingkat hari</span>
    <span class="abadge periksa">❌ ${periksa} perlu diperiksa</span>
    <span class="muted small">"Tingkat hari" = platform hanya memberi tanggal tanpa jam
      (Instagram) — jam 00:00 yang tampil bukan waktu unggah sebenarnya.</span>`;
}

/* ---------- sortir / cari / filter hasil ---------- */
let HIL = { term: "", dari: "", sampai: "", audit: "", plat: "",
            sort: "posted_at", dir: -1 };

function hasilTersaring() {
  const h = HIL;
  const term = h.term.toLowerCase();
  return (JOB?.items || []).filter((it) => {
    if (h.plat && it.platform !== h.plat) return false;
    const d = it.data || {};
    if (h.audit) {
      if (it.status !== "ok") return false;
      if ((it.audit || {}).level !== h.audit) return false;
    }
    const tgl = (d.posted_at || "").slice(0, 10);
    if (h.dari && (!tgl || tgl < h.dari)) return false;
    if (h.sampai && (!tgl || tgl > h.sampai)) return false;
    if (term) {
      const hay = `${it.url} ${d.author || ""} ${d.caption || ""} ${
        accLabel(it)}`.toLowerCase();
      if (!hay.includes(term)) return false;
    }
    return true;
  });
}

function accLabel(it) {
  if (!it.account_id) return "";
  const a = ACC_CACHE.find((x) => x.id === it.account_id);
  return a ? `${a.kode || ""} ${a.username}` : "";
}

function hasilUrut(rows) {
  const k = HIL.sort, dir = HIL.dir;
  return [...rows].sort((a, b) => {
    const da = a.data || {}, db = b.data || {};
    if (k === "url" || k === "platform" || k === "author")
      return String(da[k] ?? "").localeCompare(String(db[k] ?? ""), "id") * dir;
    if (k === "posted_at")
      return String(da.posted_at || "").localeCompare(
        String(db.posted_at || "")) * dir;
    const av = da[k] == null ? -Infinity : da[k];
    const bv = db[k] == null ? -Infinity : db[k];
    return (av === bv ? 0 : (av < bv ? -1 : 1)) * dir;
  });
}

function terapkanFilterHasil() {
  HIL.term = ($("#cariHasil")?.value || "").trim();
  HIL.dari = $("#hasilDari")?.value || "";
  HIL.sampai = $("#hasilSampai")?.value || "";
  HIL.audit = $("#filterAudit")?.value || "";
  HIL.plat = $("#filterHasilPlatform")?.value || "";
  HAL = 1;
  renderJobItems(JOB?.items || []);
  const n = hasilTersaring().length, t = (JOB?.items || []).length;
  const info = $("#hasilFilterInfo");
  if (info) info.textContent = n === t ? "" : `${n} dari ${t} link tampil`;
}

$("#cariHasil")?.addEventListener("input", terapkanFilterHasil);
["hasilDari", "hasilSampai", "filterAudit", "filterHasilPlatform"].forEach((id) =>
  $("#" + id)?.addEventListener("change", terapkanFilterHasil));
$("#btnResetFilterHasil")?.addEventListener("click", () => {
  ["cariHasil", "hasilDari", "hasilSampai"].forEach((id) => {
    if ($("#" + id)) $("#" + id).value = "";
  });
  ["filterAudit", "filterHasilPlatform"].forEach((id) => {
    if ($("#" + id)) $("#" + id).value = "";
  });
  terapkanFilterHasil();
});

// klik header untuk mengurutkan
$$("#tblHasil thead th.sortable").forEach((th) =>
  th.addEventListener("click", () => {
    const k = th.dataset.sort;
    if (HIL.sort === k) HIL.dir *= -1;
    else { HIL.sort = k; HIL.dir = -1; }
    markHasilSort();
    renderJobItems(JOB?.items || []);
  }));

function markHasilSort() {
  $$("#tblHasil thead th.sortable").forEach((th) => {
    const on = th.dataset.sort === HIL.sort;
    th.classList.toggle("sorted", on);
    th.dataset.mark = on ? (HIL.dir === -1 ? " ▼" : " ▲") : "";
  });
}

function renderJobItems(items) {
  const accById = Object.fromEntries(ACC_CACHE.map((a) => [a.id, a]));
  const okc = items.filter((i) => i.status === "ok").length;
  const failc = items.filter((i) => i.status === "failed").length;
  $("#hasilCount").textContent = `${okc} ok · ${failc} gagal · ${items.length} link`;
  const optFor = (it) => {
    const c = optCache(it.platform);
    return it.account_id && c.includes(`value="${it.account_id}"`)
      ? c.replace(`value="${it.account_id}"`, `value="${it.account_id}" selected`)
      : c;
  };
  const rowOk = (it, idx) => {
    const d = it.data;
    return `<tr>
      <td>${linkCell(it.url)}</td>
      <td>${badge(it.platform)}</td><td><b>${esc(d.author || "?")}</b></td>
      <td>${(d.posted_at || "").slice(0, 10) || "?"}</td>
      <td class="num">${fmt(d.views)}</td><td class="num">${fmt(d.like)}</td><td class="num">${fmt(d.komen)}</td>
      <td class="num">${fmt(d.share)}</td><td class="num">${fmt(d.repost)}</td>
      <td><select class="acct" data-idx="${idx}"><option value="">— pilih akun —</option>${optFor(it)}</select></td>
      <td>${statusCell(it)}${it.attempts > 1 ? ` <span class="muted small">(${it.attempts}x)</span>` : ""}</td>
      <td>${auditCell(it)}</td>
    </tr>`;
  };
  let html = "";
  renderAuditBox(items);
  markHasilSort();
  // Saring + urutkan dulu, baru paginasi.
  const semua = hasilUrut(hasilTersaring());
  const HAL_MAX = Math.max(1, Math.ceil(semua.length / PAGE_SIZE));
  if (HAL > HAL_MAX) HAL = HAL_MAX;
  const MULAI = (HAL - 1) * PAGE_SIZE;
  const iris = semua.slice(MULAI, MULAI + PAGE_SIZE);
  // kelompok per akun (yang ok)
  const groups = new Map();
  iris.forEach((it, i) => {
    if (it.status !== "ok") return;
    const idx = MULAI + i;
    const key = `acc:${it.account_id || "none"}:${it.platform}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ it, idx });
  });
  for (const [key, members] of groups) {
    const it0 = members[0].it;
    const a = accById[it0.account_id];
    const label = a ? `${esc(a.kode || "")} @${esc(a.username)}` : "belum dipasangkan — pilih manual";
    const sv = (k) => members.reduce((s, x) => s + (x.it.data[k] || 0), 0);
    const dup = members.some((x) => x.it.already_saved);
    html += `<tr class="grouphead"><td colspan="12">${badge(it0.platform)} <b>${label}</b>
      <span class="muted small"> — ${members.length} link · views ${fmt(sv("views"))} · like ${fmt(sv("like"))} · komen ${fmt(sv("komen"))} · share ${fmt(sv("share"))} · repost ${fmt(sv("repost"))}</span>
      ${dup ? `<span class="st warn"> · sebagian sudah tersimpan</span>` : ""}</td></tr>`;
    members.forEach(({ it, idx }) => { html += rowOk(it, idx); });
  }
  // yang masih jalan / antre
  const active = iris.map((it, i) => ({ it, idx: MULAI + i }))
    .filter((x) => ["pending", "running"].includes(x.it.status));
  if (active.length) {
    html += `<tr class="grouphead"><td colspan="12" class="muted">— dalam proses (${active.length}) —</td></tr>`;
    active.forEach(({ it }) => {
      html += `<tr><td>${linkCell(it.url, 50)}</td><td>${badge(it.platform)}</td>
        <td colspan="10">${statusCell(it)}</td></tr>`;
    });
  }
  // yang gagal
  const failed = iris.map((it, i) => ({ it, idx: MULAI + i }))
    .filter((x) => x.it.status === "failed");
  if (failed.length) {
    html += `<tr class="grouphead"><td colspan="12" class="st err">— gagal di halaman ini (${failed.length}) —</td></tr>`;
    failed.forEach(({ it }) => {
      html += `<tr><td>${linkCell(it.url, 50)}</td><td>${badge(it.platform)}</td>
        <td colspan="10">${statusCell(it)}</td></tr>`;
    });
  }
  const tb = $("#tblHasil tbody");
  tb.innerHTML = html;
  tb.querySelectorAll("select.acct").forEach((s) =>
    s.addEventListener("change", () => {
      const it = JOB.items[+s.dataset.idx];
      it.account_id = s.value ? +s.value : null;
    })
  );
  renderPager();
}

/* ---------- pagination ---------- */
function renderPager() {
  const bar = $("#hasilPager");
  if (!bar) return;
  const total = hasilTersaring().length;
  const halMax = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (halMax <= 1) { bar.hidden = true; return; }
  bar.hidden = false;
  const dari = (HAL - 1) * PAGE_SIZE + 1;
  const sampai = Math.min(HAL * PAGE_SIZE, total);
  bar.innerHTML = `
    <button class="btn ghost" ${HAL <= 1 ? "disabled" : ""} data-hal="-1">‹ Sebelumnya</button>
    <span class="muted small">Baris ${dari}–${sampai} dari ${total} · halaman ${HAL}/${halMax}</span>
    <button class="btn ghost" ${HAL >= halMax ? "disabled" : ""} data-hal="1">Berikutnya ›</button>`;
  bar.querySelectorAll("[data-hal]").forEach((b) =>
    b.addEventListener("click", () => {
      HAL = Math.min(halMax, Math.max(1, HAL + +b.dataset.hal));
      renderJobItems(JOB.items);
      bar.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }));
}

$("#btnSimpan").addEventListener("click", async () => {
  if (!JOB) return;
  const items = JOB.items.filter((it) => it.status === "ok" && it.account_id)
    .map((it) => ({ url: it.url, account_id: it.account_id, _data: it.data }));
  if (!items.length) return toast("Belum ada baris yang punya akun tujuan.");
  const r = await api("/api/links/save", { method: "POST", body: JSON.stringify({ items }) });
  toast(r.msg || `Tersimpan ${r.saved} postingan.`);
  $("#taLinks").value = "";
  $("#hasilCard").hidden = true;
  JOB = null;
  loadDashboard();
});

/* ---------- kelola data: hapus / reset ---------- */
let curAccId = null;

const SCOPE_LABEL = {
  platform: "platform",
  periode: "periode",
  all: "SEMUA data scrape",
  account: "akun ini",
};

async function loadDataStat() {
  const el = $("#dataStat");
  if (!el) return;
  const [c, dash] = await Promise.all([
    api("/api/posts/count?scope=all").catch(() => ({ posts: 0, metrics: 0 })),
    api("/api/counts").catch(() => ({})),
  ]);
  const nAcc = Object.values(c).reduce((a, b) => a + (b || 0), 0);
  el.innerHTML = `<span><b>${fmt(c.posts)}</b> postingan</span>
    <span><b>${fmt(c.metrics)}</b> snapshot metrik</span>
    <span><b>${nAcc}</b> akun (tetap aman, tidak ikut terhapus)</span>`;
}

function confirmScope(scope) {
  // "all" = paling berbahaya -> ketik konfirmasi + backup otomatis
  if (scope === "all") {
    const t = prompt(
      "AKAN MENGHAPUS SEMUA data scrape:\n" +
      "  · semua Posting (Views/Like/Komen/Share/Repost)\n" +
      "  · seluruh riwayat metriknya\n\n" +
      "Daftar AKUN tidak ikut terhapus.\n" +
      "Backup otomatis dibuat sebelum dihapus.\n\n" +
      "Ketik HAPUS untuk lanjut:"
    );
    if (t !== "HAPUS") { toast("Dibatalkan."); return; }
  } else if (scope === "platform") {
    const p = prompt("Hapus semua data scrape platform mana?\n" +
                     "tiktok | instagram | threads | facebook", "instagram");
    if (!p) { toast("Dibatalkan."); return; }
    scope = p.trim().toLowerCase();
  } else if (scope === "periode") {
    const { sejak, sampai } = weekRange();
    const t = prompt(`Hapus semua data scrape periode ${sejak} s.d. ${sampai}?\n` +
                     "Ketik ya untuk lanjut:", "ya");
    if (!t || t.trim().toLowerCase() !== "ya") { toast("Dibatalkan."); return; }
  }
  doDelete(scope);
}

async function doDelete(scope, platform, sejak, sampai, accountId) {
  const body = { scope, platform, sejak, sampai, account_id: accountId };
  const n = await api("/api/posts/count", { method: "POST", body: JSON.stringify(body) });
  const label = SCOPE_LABEL[scope] || scope;
  const nFollow = n.follows || 0;
  // 'all' juga mengosongkan hasil cek follow, jadi tetap lanjut walau
  // postingnya sudah kosong tapi hasil cek follow masih ada.
  if (!n.posts && !(scope === "all" && nFollow)) {
    toast("Tidak ada data untuk dihapus."); return;
  }
  const extra = scope === "all"
    ? `\n\n⚠ INI MENGHAPUS SEMUA DATA. Backup akan dibuat otomatis.` +
      (nFollow ? `\n${nFollow} hasil cek follow ikut dikosongkan.` : "")
    : `\n\n${n.metrics} baris metrik ikut terhapus.`;
  if (!confirm(`Hapus ${label}?\n\n${n.posts} Posting · ${n.metrics} metrik.${extra}`))
    return;
  const r = await api("/api/posts/delete", { method: "POST", body: JSON.stringify(body) });
  const msg = `Terhapus ${r.deleted.posts} postingan & ${r.deleted.metrics} metrik.`;
  toast(msg + (r.backup ? " Backup: " + r.backup.split("/").pop() : ""));
  loadDataStat();
  loadDashboard();
  if (curAccId) { const id = curAccId; showDetail(id); }
}

$$("[data-scope]").forEach((b) =>
  b.addEventListener("click", () => confirmScope(b.dataset.scope)));

$("#btnBackup")?.addEventListener("click", async () => {
  const r = await api("/api/backup", { method: "POST", body: "{}" });
  toast("Backup: " + r.nama);
});

$("#btnHapusPostinganAkun")?.addEventListener("click", () => {
  if (!curAccId) return;
  if (confirm("Hapus SEMUA postingan akun ini? (metrik ikut terhapus)"))
    doDelete("account", null, null, null, curAccId);
});

$("#btnTutupDetail")?.addEventListener("click", () => {
  $("#detailAkun").hidden = true;
});
$("#btnTutupPost")?.addEventListener("click", () => {
  $("#detailPost").hidden = true;
});

/* ---------- detail posting: riwayat metrik ---------- */
async function showPostHistory(postId) {
  const { post, history } = await api("/api/post/" + postId);
  $("#postMeta").innerHTML = `
    <a href="${esc(post.url)}" target="_blank" rel="noopener">${esc(post.url)}</a>
    · ${badge(post.platform)} · ${esc(post.author || "-")}
    · ${(post.posted_at || "").slice(0, 10)}
    ${post.caption ? `<br>${esc(post.caption.slice(0, 160))}` : ""}`;
  const rows = [...history].reverse();   // terbaru di atas
  $("#tblHist tbody").innerHTML = rows.map((h) => {
    const d = h.delta;
    const dv = d && d.views !== null ? d.views : null;
    return `<tr>
      <td>${esc(h.scraped_at)}</td>
      <td class="num">${fmt(h.views)}</td>
      <td class="num">${dv === null ? '<span class="muted">—</span>'
        : (dv > 0 ? `<span class="up">+${fmt(dv)}</span>`
                  : dv < 0 ? `<span class="down">${fmt(dv)}</span>` : "0")}</td>
      <td class="num">${fmt(h.like)}</td><td class="num">${fmt(h.komen)}</td>
      <td class="num">${fmt(h.share)}</td><td class="num">${fmt(h.repost)}</td></tr>`;
  }).join("");
  if (!rows.length)
    $("#tblHist tbody").innerHTML = `<tr><td colspan="7" class="muted">Belum ada metrik.</td></tr>`;
  $("#detailPost").hidden = false;
  $("#detailPost").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

/* ---------- akun ---------- */
let akunSemua = [];        // cache terakhir dari /api/accounts
let akunTerpilih = new Set();

function akunTersaring() {
  const q = ($("#cariAkun")?.value || "").trim().toLowerCase();
  const p = $("#filterAkunPlatform")?.value || "";
  return akunSemua.filter((a) => {
    if (p && a.platform !== p) return false;
    if (!q) return true;
    return (a.username || "").toLowerCase().includes(q)
        || (a.kode || "").toLowerCase().includes(q);
  });
}

function renderAkun() {
  const rows = akunTersaring();
  const total = akunSemua.length;
  $("#akunCount").textContent =
    rows.length === total ? total + " akun"
                          : `${rows.length} / ${total} akun`;
  $("#tblAkun tbody").innerHTML = rows.length ? rows.map((a) => `
    <tr>
      <td><input type="checkbox" data-pick="${a.id}" ${akunTerpilih.has(a.id) ? "checked" : ""}></td>
      <td>${a.kode ?? ""}</td><td>${badge(a.platform)}</td>
      <td><b>${esc(a.username)}</b></td>
      <td class="num">${a.n_post ? fmt(a.n_post) : '<span class="muted">0</span>'}</td>
      <td>${a.link_profile ? linkCell(a.link_profile, 36) : ""}</td>
      <td><button class="btn ghost" data-del="${a.id}" data-n="${a.n_post}">hapus</button></td>
    </tr>`).join("")
    : `<tr><td colspan="7" class="muted" style="text-align:center;padding:18px">
         ${total ? "Tidak ada akun yang cocok dengan filter." : "Belum ada akun. Import dari Excel PEMANTAUAN."}
       </td></tr>`;

  $$("#tblAkun [data-pick]").forEach((c) =>
    c.addEventListener("change", () => {
      const id = +c.dataset.pick;
      c.checked ? akunTerpilih.add(id) : akunTerpilih.delete(id);
      $("#jmlTerpilih").textContent = akunTerpilih.size;
      $("#btnHapusTerpilih").disabled = !akunTerpilih.size;
    }));
  $$("#tblAkun [data-del]").forEach((b) =>
    b.addEventListener("click", async () => {
      const n = b.dataset.n;
      if (!confirm(
        "Hapus akun ini beserta SEMUA postingannya?\n\n"
        + (n && n !== "0" ? `${n} postingan + metrik ikut terhapus.\n\n` : "")
        + "Backup otomatis dibuat.")) return;
      await api("/api/accounts/" + b.dataset.del, { method: "DELETE" });
      akunTerpilih.delete(+b.dataset.del);
      toast("Akun dihapus.");
      loadAkun(); updateCounts();
    }));

  // header checkbox: hanya yang tampil (terfilter)
  $("#chkSemua").checked = rows.length > 0 && rows.every((a) => akunTerpilih.has(a.id));
  $("#jmlTerpilih").textContent = akunTerpilih.size;
  $("#btnHapusTerpilih").disabled = !akunTerpilih.size;
}

async function loadAkun() {
  akunSemua = await api("/api/accounts");
  // buang pilihan yang akunnya sudah tidak ada
  const ada = new Set(akunSemua.map((a) => a.id));
  akunTerpilih = new Set([...akunTerpilih].filter((id) => ada.has(id)));
  renderAkun();
}

$("#cariAkun")?.addEventListener("input", renderAkun);
$("#filterAkunPlatform")?.addEventListener("change", renderAkun);

$("#chkSemua")?.addEventListener("change", (e) => {
  akunTersaring().forEach((a) => {
    e.target.checked ? akunTerpilih.add(a.id) : akunTerpilih.delete(a.id);
  });
  renderAkun();
});

$("#btnPilihSemua")?.addEventListener("click", () => {
  const rows = akunTersaring();
  const semuaDipilih = rows.every((a) => akunTerpilih.has(a.id));
  rows.forEach((a) => semuaDipilih ? akunTerpilih.delete(a.id) : akunTerpilih.add(a.id));
  renderAkun();
});

$("#btnHapusTerpilih")?.addEventListener("click", async () => {
  const ids = [...akunTerpilih];
  if (!ids.length) return toast("Belum ada akun dipilih.");
  const totalPost = akunSemua
    .filter((a) => akunTerpilih.has(a.id))
    .reduce((s, a) => s + (a.n_post || 0), 0);
  if (!confirm(
    `Hapus ${ids.length} akun terpilih?\n\n`
    + (totalPost ? `±${totalPost} postingan + metrik ikut terhapus.\n\n` : "")
    + "Backup otomatis dibuat.")) return;
  const r = await api("/api/accounts", { method: "DELETE", body: JSON.stringify({ ids }) });
  const d = r.deleted || {};
  toast(`Terhapus ${d.accounts} akun, ${d.posts} postingan, ${d.metrics} metrik.`
        + (r.backup ? " Backup: " + r.backup.split("/").pop() : ""));
  akunTerpilih.clear();
  $("#detailAkun").hidden = true;
  curAccId = null;
  loadAkun(); updateCounts(); loadDashboard();
});

$("#btnHapusSemuaAkun")?.addEventListener("click", async () => {
  if (!akunSemua.length) return toast("Belum ada akun.");
  const t = prompt(
    "AKAN MENGHAPUS SELURUH DAFTAR AKUN:\n\n"
    + `  · ${akunSemua.length} akun\n`
    + "  · semua postingan belonging akun-akun itu\n"
    + "  · seluruh riwayat metriknya\n\n"
    + (db_note()) + "\n"
    + "Backup otomatis dibuat sebelum dihapus.\n"
    + "Daftar akun bisa di-import ulang dari Excel PEMANTAUAN.\n\n"
    + "Ketik HAPUS untuk lanjut:");
  if (t !== "HAPUS") { toast("Dibatalkan."); return; }
  const r = await api("/api/accounts", { method: "DELETE", body: JSON.stringify({ all: true }) });
  const d = r.deleted || {};
  toast(`Terhapus ${d.accounts} akun, ${d.posts} postingan, ${d.metrics} metrik.`
        + (r.backup ? " Backup: " + r.backup.split("/").pop() : ""));
  akunTerpilih.clear();
  $("#detailAkun").hidden = true;
  curAccId = null;
  loadAkun(); updateCounts(); loadDashboard(); loadDataStat();
});

function db_note() {
  const n = akunSemua.reduce((s, a) => s + (a.n_post || 0), 0);
  return n ? `  · ${n} posting ikut terhapus (cascade otomatis)\n` : "";
}
$("#formAkun").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  await api("/api/accounts", { method: "POST", body: JSON.stringify(f) });
  e.target.reset();
  loadAkun(); updateCounts();
  toast("Akun ditambahkan.");
});
$("#btnImportExcel").addEventListener("click", async () => {
  const f = $("#fileExcel").files[0];
  if (!f) return toast("Pilih dulu file Excel PEMANTAUAN (.xlsx / .csv).");
  const fd = new FormData();
  fd.append("file", f);
  try {
    const r = await fetch("/api/accounts/import-excel", { method: "POST", body: fd });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) return toast("Gagal: " + (j.error || ("HTTP " + r.status)));
    const pp = j.per_platform || {};
    const rinc = Object.entries(pp).map(([k, v]) => `${k}: ${v}`).join(", ");
    toast(`Import selesai: ${j.imported} akun${rinc ? " (" + rinc + ")" : ""}.`);
    $("#fileExcel").value = "";
    loadAkun(); updateCounts();
  } catch (e) {
    toast("Gagal: " + e.message);
  }
});

/* ---------- pengaturan ---------- */
async function loadSettings() {
  const s = await api("/api/settings");
  $("#setDelay").value = s.scrape_delay || 2;
  for (const p of ["threads", "instagram", "facebook"]) {
    const el = $("#lw_" + p);
    if (el) el.value = s.lane_workers?.[p] || "3";
  }
  await loadSessions();
}
$("#btnSimpanLane")?.addEventListener("click", async () => {
  const body = {};
  for (const p of ["threads", "instagram", "facebook"]) {
    const el = $("#lw_" + p);
    if (el) body["lane_workers_" + p] = el.value;
  }
  await api("/api/settings", { method: "POST", body: JSON.stringify(body) });
  toast("Kecepatan scrape disimpan.");
});
$("#btnSimpanSet").addEventListener("click", async () => {
  await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({ scrape_delay: $("#setDelay").value }),
  });
  toast("Pengaturan disimpan.");
});
/* ---------- sesi login ---------- */
const SESS_UNLOCK = {
  instagram: "daftar postingan per akun",
  threads: "view count postingan",
  facebook: "baca postingan FB",
};
// TikTok tidak ada di sini: riset membuktikan sesi cookie via Python tidak
// membuka listing TikTok (daftar video tidak ada di SSR; API butuh signing).
function renderSessCards(status) {
  $("#sessGrid").innerHTML = Object.keys(SESS_UNLOCK).map((p) => {
    const st = (status && status[p]) || { active: false, n_cookies: 0 };
    return `<div class="sess-card" data-p="${p}">
      <div class="row between">
        <b>${PLAT[p]}</b>
        <span class="pill ${st.active ? "on" : "off"}" id="sessPill-${p}">${st.active ? "● aktif (" + st.n_cookies + ")" : "○ belum ada"}</span>
      </div>
      <div class="muted small">Membuka: ${SESS_UNLOCK[p]}</div>
      <textarea id="sessTxt-${p}" rows="2" placeholder="Tempel cookie di sini — atau upload file di bawah"></textarea>
      <div class="row gap">
        <label class="btn small">📁 Upload cookies.txt<input type="file" id="sessFile-${p}" accept=".txt" hidden></label>
        <button class="btn small primary" data-act="save" data-p="${p}">Simpan</button>
        <button class="btn small" data-act="test" data-p="${p}">Tes sesi</button>
        <button class="btn small danger" data-act="del" data-p="${p}">Hapus</button>
      </div>
      <div class="muted small" id="sessMsg-${p}"></div>
    </div>`;
  }).join("");
  $$("#sessGrid [data-act]").forEach((b) => b.addEventListener("click", () => sessAct(b.dataset.act, b.dataset.p)));
  $$("#sessGrid input[type=file]").forEach((f) => f.addEventListener("change", () => sessUpload(f)));
}
async function sessAct(act, p) {
  const msg = $(`#sessMsg-${p}`);
  try {
    if (act === "save") {
      const cookie = $(`#sessTxt-${p}`).value.trim();
      if (!cookie) { msg.textContent = "Tempel dulu cookie-nya, atau upload file."; return; }
      const r = await api("/api/sessions", { method: "POST", body: JSON.stringify({ platform: p, cookie }) });
      msg.textContent = `Tersimpan (${r.n_cookies} cookie). Klik “Tes sesi” untuk verifikasi.`;
      $(`#sessTxt-${p}`).value = "";
    } else if (act === "test") {
      msg.textContent = "Mengetes…";
      const r = await api(`/api/sessions/${p}/test`, { method: "POST" });
      msg.textContent = (r.ok ? "✅ " : "❌ ") + r.detail;
    } else if (act === "del") {
      await api(`/api/sessions/${p}`, { method: "DELETE" });
      msg.textContent = "Sesi dihapus.";
    }
    loadSessions();
  } catch (e) { msg.textContent = "❌ " + e.message; }
}
async function sessUpload(input) {
  const card = input.closest(".sess-card");
  const p = card.dataset.p;
  const msg = $(`#sessMsg-${p}`);
  const f = input.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  fd.append("platform", p);
  try {
    const r = await fetch("/api/sessions/upload", { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
    msg.textContent = `Tersimpan dari file (${j.n_cookies} cookie). Klik “Tes sesi”.`;
    loadSessions();
  } catch (e) { msg.textContent = "❌ " + e.message; }
  input.value = "";
}
async function loadSessions() {
  const s = await api("/api/sessions").catch(() => ({}));
  renderSessCards(s);
  const ig = s.instagram && s.instagram.active;
  $("#bulkNote").textContent = ig
    ? "Sesi Instagram aktif — tarik massal siap jalan."
    : "Catatan: Instagram belum ada sesi — tombol tarik massal akan gagal dengan pesan jelas.";
}
/* ---------- tarik massal instagram ---------- */
// CATATAN: progress bar di halaman Pengaturan punya ID sendiri
// (jobProgSet/jobBarSet/jobTxtSet). Sebelumnya keduanya memakai id yang sama
// dengan view Input Link, sehingga $("#jobProg") hanya menemukan elemen
// PERTAMA (yang ada di view tersembunyi) -> progress bar tidak pernah
// terlihat di Pengaturan.
function pollBulkJob(job_id, label) {
  $("#jobProgSet").hidden = false;
  const poll = setInterval(async () => {
    const j = await api("/api/jobs/" + job_id);
    const pct = j.total ? Math.round((100 * j.done) / j.total) : 0;
    $("#jobBarSet").style.width = pct + "%";
    $("#jobTxtSet").textContent = `${label}: ${j.done}/${j.total} akun — ok ${j.ok}, gagal ${j.fail}`;
    if (j.status === "done") {
      clearInterval(poll);
      const saved = j.result && j.result.saved;
      const err = j.result && j.result.error;
      toast(err ? ("❌ " + err) : `Selesai: ${j.ok} akun ok, ${j.fail} gagal${saved ? ", " + saved + " postingan tersimpan" : ""}.`);
      loadDashboard();
    }
  }, 2000);
}
$("#btnIgBulk").addEventListener("click", async () => {
  try {
    const { job_id } = await api("/api/instagram/fetch", {
      method: "POST", body: JSON.stringify({ limit: +$("#bulkLimit").value || 10 }),
    });
    pollBulkJob(job_id, "Instagram");
  } catch (e) { toast("❌ " + e.message); }
});
$("#btnThreads").addEventListener("click", async () => {
  const { sejak, sampai } = weekRange();
  const { job_id } = await api("/api/threads/fetch", {
    method: "POST", body: JSON.stringify({ sejak, sampai }),
  });
  $("#jobProgSet").hidden = false;
  const poll = setInterval(async () => {
    const j = await api("/api/jobs/" + job_id);
    const pct = j.total ? Math.round((100 * j.done) / j.total) : 0;
    $("#jobBarSet").style.width = pct + "%";
    $("#jobTxtSet").textContent = `${j.done}/${j.total} akun — ok ${j.ok}, gagal ${j.fail}`;
    if (j.status === "done") {
      clearInterval(poll);
      toast(`Selesai: ${j.ok} akun ok, ${j.fail} gagal.`);
      loadDashboard();
    }
  }, 2000);
});

/* ---------- cek follow (relasi vs akun admin) ----------
   Fitur ini memakai jalur API privat Instagram, jadi butuh cookie sesi.
   Status dihitung dari baris follow_status (lihat db.py):
     pending  -> permintaan follow masih menunggu (target privat)
     mutual   -> admin follow DAN target follow balik
     following-> admin sudah follow, target belum balik
     followed_by -> target follow admin, admin belum follow
     none     -> tidak saling follow
     error    -> gagal dicek (sesi/limit/akun hilang)              */
let FOLLOW = [];

function followStatus(r) {
  if (r.error) return "error";
  if (!r.checked_at) return "unchecked";
  if (r.outgoing_request) return "pending";
  if (r.following && r.followed_by) return "mutual";
  if (r.following) return "following";
  if (r.followed_by) return "followed_by";
  return "none";
}

const FOLLOW_LABEL = {
  mutual: ['ok', '✅ Saling follow'],
  following: ['ok', '→ Admin follow, belum balik'],
  followed_by: ['warn', '← Mereka follow, admin belum'],
  none: ['warn', '✖ Belum saling follow'],
  pending: ['warn', '⏳ Menunggu izin (privat)'],
  error: ['err', '❌ Gagal dicek'],
  unchecked: ['', '◦ Belum dicek'],
};

function renderFollow() {
  const term = ($("#cariFollow").value || "").toLowerCase();
  const f = $("#filterFollow").value;
  const rows = FOLLOW.filter((r) => {
    if (f && followStatus(r) !== f) return false;
    if (!term) return true;
    return (`${r.kode || ""} ${r.username || ""}`).toLowerCase().includes(term);
  });
  const tb = $("#tblFollow tbody");
  tb.innerHTML = "";
  rows.forEach((r) => {
    const st = followStatus(r);
    const [cls, label] = FOLLOW_LABEL[st] || ['', st];
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td>${r.kode ?? ""}</td>` +
      `<td>${r.username || ""}</td>` +
      `<td class="num">${fmt(r.follower_count)}</td>` +
      `<td class="num">${fmt(r.following_count)}</td>` +
      `<td><span class="st ${cls}">${label}</span></td>` +
      `<td>${r.is_private ? "ya" : (r.checked_at ? "tidak" : "")}</td>` +
      `<td class="small">${r.checked_at || "—"}</td>` +
      `<td class="small" title="${(r.error || "").replace(/"/g, "&quot;")}">` +
      `${(r.error || "").slice(0, 70)}</td>`;
    tb.appendChild(tr);
  });
  $("#followEmpty").hidden = rows.length > 0;
  $("#followFilterInfo").textContent = `${rows.length}/${FOLLOW.length} akun`;
}

function renderFollowStats(k) {
  const items = [
    ["Total akun", k.total], ["Sudah dicek", k.checked],
    ["Saling follow", k.mutual], ["Admin follow", k.following],
    ["Mereka follow", k.followed_by], ["Belum saling", k.none],
    ["Menunggu izin", k.pending], ["Gagal", k.error],
    ["Belum dicek", k.unchecked],
  ];
  $("#followStats").innerHTML = items.map(([k2, v]) =>
    `<div class="stat"><div class="k">${k2}</div><div class="v">${fmt(v)}</div></div>`
  ).join("");
}

async function loadFollow() {
  const d = await api("/api/follow?platform=instagram").catch(() => null);
  if (!d) return;
  FOLLOW = d.rows || [];
  $("#followCount").textContent = `${FOLLOW.length} akun`;
  $("#followAdmin").textContent = d.admin
    ? `Dicek relatif terhadap akun admin: @${d.admin}`
    : "Akun admin belum terbaca (jalankan cek follow sekali).";
  $("#followWarn").hidden = !!d.sesi_aktif;
  renderFollowStats(d.ringkasan || {});
  renderFollow();
}

$("#btnMuatFollow")?.addEventListener("click", loadFollow);
["cariFollow", "filterFollow"].forEach((id) =>
  $("#" + id)?.addEventListener("input", renderFollow));

$("#btnCekFollow")?.addEventListener("click", async () => {
  const btn = $("#btnCekFollow");
  btn.disabled = true;
  try {
    const { job_id } = await api("/api/follow/check", {
      method: "POST", body: JSON.stringify({ platform: "instagram" }),
    });
    $("#followProg").hidden = false;
    const poll = setInterval(async () => {
      const j = await api("/api/jobs/" + job_id).catch(() => null);
      if (!j) return;
      const pct = j.total ? Math.round((100 * j.done) / j.total) : 0;
      $("#followBar").style.width = pct + "%";
      const admin = (j.admin && j.admin.username) ? ` (@${j.admin.username})` : "";
      $("#followTxt").textContent =
        `${j.done}/${j.total} akun${admin} — ok ${j.ok}, gagal ${j.fail}`;
      if (j.status === "done") {
        clearInterval(poll);
        btn.disabled = false;
        const err = j.result && j.result.error;
        if (err) toast("❌ " + err);
        else toast(`Selesai: ${j.ok} akun dicek, ${j.fail} gagal.`);
        if (j.auth_stopped) toast("⚠ Sesi Instagram bermasalah — isi ulang cookie.");
        loadFollow();
      }
    }, 2000);
  } catch (e) {
    btn.disabled = false;
    toast("❌ " + e.message);
  }
});

/* ---------- topbar ---------- */
$("#btnPekanIni").addEventListener("click", () => { defaultWeek(); loadDashboard(); });
$("#btnExport").addEventListener("click", () => {
  const { sejak, sampai } = weekRange();
  const plat = $("#filterPlatform").value;
  const q = new URLSearchParams({
    sejak, sampai,
    format: $("#exportFormat")?.value || "xlsx",
    ...(plat ? { platform: plat } : {}) });
  window.location = "/api/export?" + q;
});
$("#btnRefresh")?.addEventListener("click", async () => {
  $("#btnRefresh").disabled = true;
  try {
    await Promise.all([loadDashboard(), loadDataStat(), updateCounts()]);
    toast("Data dimuat ulang.");
  } finally {
    $("#btnRefresh").disabled = false;
  }
});
["sejak", "sampai", "filterPlatform"].forEach((id) =>
  $("#" + id).addEventListener("change", loadDashboard)
);
$("#cari").addEventListener("input", loadDashboard);

/* ---------- init ---------- */
defaultWeek();
loadDashboard();
