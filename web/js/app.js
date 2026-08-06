/* 教师招聘聚合站 - 前端逻辑（vanilla JS，无构建步骤） */
"use strict";

const DATA_URL = "data/jobs.json";
const META_URL = "data/meta.json";
const COUNTS_URL = "data/province-counts.json";

// 省级行政区 → 地图中心坐标（近似值，仅用于热度分布）
const PROVINCE_COORDS = {
  "北京": [40.18, 116.41], "天津": [39.08, 117.20], "上海": [31.23, 121.47], "重庆": [29.56, 106.55],
  "河北": [38.04, 114.51], "山西": [37.87, 112.55], "辽宁": [41.80, 123.43], "吉林": [43.89, 125.32],
  "黑龙江": [45.80, 126.53], "江苏": [32.06, 118.80], "浙江": [30.27, 120.15], "安徽": [31.86, 117.28],
  "福建": [26.07, 119.30], "江西": [28.68, 115.86], "山东": [36.65, 117.12], "河南": [34.75, 113.63],
  "湖北": [30.59, 114.31], "湖南": [28.23, 112.94], "广东": [23.13, 113.26], "海南": [20.02, 110.35],
  "四川": [30.57, 104.06], "贵州": [26.65, 106.63], "云南": [25.04, 102.71], "陕西": [34.27, 108.94],
  "甘肃": [36.06, 103.83], "青海": [36.62, 101.78], "台湾": [25.03, 121.56], "内蒙古": [40.84, 111.75],
  "广西": [22.82, 108.32], "西藏": [29.65, 91.14], "宁夏": [38.47, 106.27], "新疆": [43.83, 87.62],
  "香港": [22.32, 114.17], "澳门": [22.20, 113.55],
};

const state = {
  jobs: [],
  meta: null,
  filters: { q: "", province: "", subject: "", education: "", level: "", source: "", days: "", today: false },
  sort: "date",
  pageSize: 20,
  page: 1,
  map: null,
  mapInit: false,
  watches: [],
};

const $ = (id) => document.getElementById(id);
const els = {
  search: $("search"), sort: $("sort"), province: $("f-province"), subject: $("f-subject"),
  education: $("f-education"), level: $("f-level"), source: $("f-source"), days: $("f-days"),
  list: $("job-list"), empty: $("empty"), count: $("stat-count"), updated: $("stat-updated"),
  listCount: $("list-count"), listTitle: $("list-title"), chips: $("active-chips"),
  loadMore: $("load-more"), mapPanel: $("map-panel"), btnToday: $("btn-today"),
  btnSaveWatch: $("btn-save-watch"), watchList: $("watch-list"), watchInfo: $("watch-info"),
};

/* ---------- 数据加载 ---------- */
async function loadData() {
  try {
    const [data, meta] = await Promise.all([
      fetch(DATA_URL).then((r) => r.json()),
      fetch(META_URL).then((r) => r.json()).catch(() => null),
    ]);
    state.jobs = data.jobs || [];
    state.meta = meta;
    els.count.textContent = `共 ${state.jobs.length} 个岗位`;
    if (data.updated_at) {
      els.updated.textContent = "更新于 " + formatDateTime(data.updated_at);
    }
    buildFilterOptions();
    loadWatches();
    render();
    loadCounts();
  } catch (e) {
    els.count.textContent = "数据加载失败";
    els.updated.textContent = "请稍后刷新重试";
    console.error("loadData error:", e);
  }
}

async function loadCounts() {
  try {
    const counts = await fetch(COUNTS_URL).then((r) => r.json());
    renderProvinceBars(counts.counts || {});
  } catch (e) {
    /* 地图数据非关键路径，失败静默 */
  }
}

/* ---------- 筛选选项 ---------- */
function buildFilterOptions() {
  fillSelect(els.province, "全部地区", collect(state.jobs, (j) => j.province));
  fillSelect(els.subject, "全部学科", collect(state.jobs, (j) => j.subject));
  fillSelect(els.education, "全部学历", collect(state.jobs, (j) => j.education));
  fillSelect(els.level, "全部学段", collect(state.jobs, (j) => j.school_level));
  fillSelect(els.source, "全部来源", collect(state.jobs, (j) => j.source_label));
}

function collect(jobs, getter) {
  const map = new Map();
  for (const j of jobs) {
    const v = getter(j);
    if (!v) continue;
    map.set(v, (map.get(v) || 0) + 1);
  }
  return [...map.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k);
}

function fillSelect(select, placeholder, values) {
  select.innerHTML = `<option value="">${placeholder}</option>` +
    values.map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("");
}

/* ---------- 筛选与排序 ---------- */
function applyFilters() {
  const f = state.filters;
  let list = state.jobs;
  if (f.q) {
    const q = f.q.toLowerCase();
    list = list.filter((j) =>
      [j.title, j.school, j.subject, j.city, j.province, j.source_label, j.summary]
        .join(" ").toLowerCase().includes(q)
    );
  }
  if (f.province) list = list.filter((j) => j.province === f.province);
  if (f.subject) list = list.filter((j) => j.subject === f.subject);
  if (f.education) list = list.filter((j) => j.education === f.education);
  if (f.level) list = list.filter((j) => j.school_level === f.level);
  if (f.source) list = list.filter((j) => j.source_label === f.source);
  if (f.days) {
    const cutoff = Date.now() - Number(f.days) * 86400000;
    list = list.filter((j) => {
      const d = (j.publish_date || j.crawl_date) ? new Date(j.publish_date || j.crawl_date).getTime() : 0;
      return d >= cutoff;
    });
  }
  if (f.today) {
    list = list.filter((j) => j.is_new);
  }
  // 默认按时间倒序：优先 publish_date，缺失时用 crawl_date
  if (state.sort === "date") {
    list = [...list].sort((a, b) => {
      const da = a.publish_date || a.crawl_date || "";
      const db = b.publish_date || b.crawl_date || "";
      return db.localeCompare(da);
    });
  }
  if (state.sort === "salary") {
    list = [...list].sort((a, b) => parseSalary(b) - parseSalary(a));
  }
  return list;
}

function parseSalary(j) {
  const text = j.salary_text || j.salary || "";
  const m = text.match(/(\d+(?:\.\d+)?)\s*[-~至到]\s*(\d+(?:\.\d+)?)/);
  if (!m) return 0;
  const lo = parseFloat(m[1]);
  const hi = parseFloat(m[2]);
  const unit = text.includes("万") || text.includes("W") ? 10000 : 1000; // K/月 或 万
  const months = text.includes("年") ? 12 : 1;
  const annual = (lo + hi) / 2 * unit * months;
  return isNaN(annual) ? 0 : annual;
}

/* ---------- 渲染 ---------- */
function render() {
  const filtered = applyFilters();
  state.page = 1;
  renderPage(filtered);
  renderChips();
}

function renderPage(filtered) {
  const total = filtered.length;
  els.listCount.textContent = total ? `共 ${total} 条` : "";
  const end = Math.min(state.page * state.pageSize, total);
  const slice = filtered.slice(0, end);
  els.list.innerHTML = slice.map(renderCard).join("");
  els.empty.classList.toggle("hidden", total > 0);
  els.loadMore.parentElement.classList.toggle("hidden", end >= total);
  els.listTitle.textContent = total ? `招聘信息（${total}）` : "招聘信息";
}

function renderCard(j) {
  const tags = [];
  if (j.is_new) tags.push(`<span class="tag new">🆕 今日新增</span>`);
  if (j.salary_text) tags.push(`<span class="tag salary">${escapeHtml(j.salary_text)}</span>`);
  if (j.province || j.city) tags.push(`<span class="tag loc">📍 ${escapeHtml(j.province || "")}${j.city ? "·" + escapeHtml(j.city) : ""}</span>`);
  if (j.education) tags.push(`<span class="tag edu">🎓 ${escapeHtml(j.education)}</span>`);
  if (j.subject) tags.push(`<span class="tag">📖 ${escapeHtml(j.subject)}</span>`);
  if (j.school_level) tags.push(`<span class="tag">🏫 ${escapeHtml(j.school_level)}</span>`);
  if (j.experience) tags.push(`<span class="tag">⏳ ${escapeHtml(j.experience)}</span>`);
  if (j.deadline) {
    const near = isNearDeadline(j.deadline);
    tags.push(`<span class="tag ${near ? "hot" : ""}">🕛 截止 ${escapeHtml(j.deadline)}</span>`);
  }
  const pub = j.publish_date
    ? formatDate(j.publish_date)
    : (j.crawl_date ? `${formatDate(j.crawl_date)} 抓取` : "日期未知");
  return `
    <li class="job-card">
      <div class="job-top">
        <div>
          <a class="job-title" href="${escapeAttr(j.url)}" target="_blank" rel="noopener nofollow">${escapeHtml(j.title)}</a>
          ${j.school ? `<p class="job-school">🏫 ${escapeHtml(j.school)}</p>` : ""}
        </div>
      </div>
      <div class="job-tags">${tags.join("")}</div>
      <div class="job-meta">
        <span>${pub}</span>
        <span class="right">
          <span class="source-pill">${escapeHtml(j.source_label || j.source || "")}</span>
          <a class="job-link" href="${escapeAttr(j.url)}" target="_blank" rel="noopener nofollow">查看原文 →</a>
        </span>
      </div>
    </li>`;
}

function renderChips() {
  const f = state.filters;
  const chips = [];
  if (f.q) chips.push(["关键词", f.q, "q"]);
  if (f.today) chips.push(["时间", "今日新增", "today"]);
  if (f.province) chips.push(["地区", f.province, "province"]);
  if (f.subject) chips.push(["学科", f.subject, "subject"]);
  if (f.education) chips.push(["学历", f.education, "education"]);
  if (f.level) chips.push(["学段", f.level, "level"]);
  if (f.source) chips.push(["来源", f.source, "source"]);
  if (f.days) chips.push(["时间", `最近 ${f.days} 天`, "days"]);
  els.chips.innerHTML = chips
    .map(([label, value, key]) =>
      `<span class="chip">${escapeHtml(label)}：${escapeHtml(value)} <button data-key="${key}" aria-label="移除筛选">×</button></span>`
    )
    .join("");
  els.chips.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => {
      const key = b.dataset.key;
      state.filters[key] = "";
      if (key === "q") els.search.value = "";
      syncSelects();
      render();
    });
  });
}

function syncSelects() {
  els.search.value = state.filters.q;
  els.province.value = state.filters.province;
  els.subject.value = state.filters.subject;
  els.education.value = state.filters.education;
  els.level.value = state.filters.level;
  els.source.value = state.filters.source;
  els.days.value = state.filters.days;
  els.btnToday.classList.toggle("active", state.filters.today);
  els.btnToday.setAttribute("aria-pressed", String(state.filters.today));
}

/* ---------- 关注筛选组合（localStorage） ---------- */
const WATCH_KEY = "teacher-hire-watches";

function loadWatches() {
  try {
    state.watches = JSON.parse(localStorage.getItem(WATCH_KEY) || "[]");
  } catch (e) {
    state.watches = [];
  }
  renderWatches();
}

function saveWatches() {
  localStorage.setItem(WATCH_KEY, JSON.stringify(state.watches.slice(0, 8)));
  renderWatches();
}

function currentFilterSignature() {
  const f = state.filters;
  return [f.province, f.subject, f.education, f.level].join("|");
}

function renderWatches() {
  const todayNew = state.jobs.filter((j) => j.is_new);
  els.watchList.innerHTML = state.watches.map((w) => {
    const matchToday = todayNew.filter((j) =>
      (!w.province || j.province === w.province) &&
      (!w.subject || j.subject === w.subject) &&
      (!w.education || j.education === w.education) &&
      (!w.level || j.school_level === w.level)
    ).length;
    const label = [w.province, w.subject, w.education, w.level].filter(Boolean).join(" · ") || "全部岗位";
    const badge = matchToday > 0 ? `<span class="new-badge">+${matchToday}</span>` : "";
    return `<span class="watch-item" data-idx="${state.watches.indexOf(w)}">⭐ ${escapeHtml(label)}${badge}<button data-del="1" aria-label="删除">×</button></span>`;
  }).join("");
  els.watchList.querySelectorAll(".watch-item").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (e.target.dataset.del) {
        state.watches.splice(Number(el.dataset.idx), 1);
        saveWatches();
        return;
      }
      const w = state.watches[Number(el.dataset.idx)];
      if (!w) return;
      state.filters.province = w.province || "";
      state.filters.subject = w.subject || "";
      state.filters.education = w.education || "";
      state.filters.level = w.level || "";
      syncSelects();
      render();
    });
  });
}

function saveCurrentWatch() {
  const f = state.filters;
  const w = { province: f.province || "", subject: f.subject || "", education: f.education || "", level: f.level || "" };
  if (currentFilterSignature() === "|||" && !f.q) {
    els.watchInfo.textContent = "先选择筛选条件再保存～";
    setTimeout(() => { els.watchInfo.textContent = ""; }, 2000);
    return;
  }
  const sig = [w.province, w.subject, w.education, w.level].join("|");
  if (state.watches.some((x) => [x.province, x.subject, x.education, x.level].join("|") === sig)) {
    els.watchInfo.textContent = "这个组合已经关注过了";
    setTimeout(() => { els.watchInfo.textContent = ""; }, 2000);
    return;
  }
  state.watches.push(w);
  saveWatches();
  els.watchInfo.textContent = "已保存，有新岗位会显示 +N 角标";
  setTimeout(() => { els.watchInfo.textContent = ""; }, 2500);
}

/* ---------- 地图与省份统计 ---------- */
function renderProvinceBars(counts) {
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  $("province-bars").innerHTML = sorted
    .map(([p, c]) => `<span class="pbar" data-prov="${escapeAttr(p)}"><strong>${escapeHtml(p)}</strong> ${c}</span>`)
    .join("");
  document.querySelectorAll(".pbar").forEach((el) => {
    el.addEventListener("click", () => {
      state.filters.province = state.filters.province === el.dataset.prov ? "" : el.dataset.prov;
      els.province.value = state.filters.province;
      render();
    });
  });
}

function initMap(counts) {
  if (!window.L) return;
  if (!state.mapInit) {
    state.map = window.L.map("map").setView([34.5, 108.0], 4);
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 10,
    }).addTo(state.map);
    state.mapInit = true;
  }
  state.map.eachLayer((l) => {
    if (l instanceof window.L.CircleMarker) state.map.removeLayer(l);
  });
  const entries = Object.entries(counts).filter(([p]) => PROVINCE_COORDS[p]);
  const max = Math.max(1, ...entries.map(([, c]) => c));
  const latLngs = [];
  for (const [prov, count] of entries) {
    const [lat, lng] = PROVINCE_COORDS[prov];
    latLngs.push([lat, lng]);
    const r = 6 + Math.sqrt(count / max) * 18;
    const marker = window.L.circleMarker([lat, lng], {
      radius: r,
      color: "#2f6fed",
      weight: 1,
      fillColor: "#2f6fed",
      fillOpacity: 0.55,
    }).addTo(state.map);
    marker.bindPopup(`<b>${prov}</b><br/>${count} 个岗位`);
    marker.on("click", () => {
      state.filters.province = state.filters.province === prov ? "" : prov;
      els.province.value = state.filters.province;
      render();
    });
  }
  if (latLngs.length > 1) state.map.fitBounds(window.L.latLngBounds(latLngs), { padding: [20, 20] });
}

/* ---------- 工具函数 ---------- */
function formatDate(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso || "";
  const diff = (Date.now() - d.getTime()) / 86400000;
  if (diff >= 0 && diff < 1) return "今天";
  if (diff >= 1 && diff < 2) return "昨天";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function formatDateTime(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso || "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function isNearDeadline(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return false;
  return (d.getTime() - Date.now()) < 5 * 86400000;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, "&quot;");
}

/* ---------- 事件绑定 ---------- */
function bindEvents() {
  let debounce;
  els.search.addEventListener("input", (e) => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.filters.q = e.target.value.trim();
      render();
    }, 250);
  });
  els.sort.addEventListener("change", (e) => {
    state.sort = e.target.value;
    render();
  });
  const bindSelect = (sel, key) => sel.addEventListener("change", () => {
    state.filters[key] = sel.value;
    render();
  });
  bindSelect(els.province, "province");
  bindSelect(els.subject, "subject");
  bindSelect(els.education, "education");
  bindSelect(els.level, "level");
  bindSelect(els.source, "source");
  bindSelect(els.days, "days");

  els.loadMore.addEventListener("click", () => {
    state.page += 1;
    renderPage(applyFilters());
  });
  els.btnToday.addEventListener("click", () => {
    state.filters.today = !state.filters.today;
    syncSelects();
    render();
  });
  els.btnSaveWatch.addEventListener("click", saveCurrentWatch);
  els.mapPanel.addEventListener("toggle", () => {
    if (els.mapPanel.open && !state.mapInit) {
      fetch(COUNTS_URL).then((r) => r.json()).then((d) => initMap(d.counts || {}))
        .catch(() => {});
      setTimeout(() => state.map && state.map.invalidateSize(), 100);
    }
  });
}

bindEvents();
loadData();
