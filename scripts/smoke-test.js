/* 前端冒烟测试：极简 DOM shim（无需 jsdom/浏览器依赖）
 *
 * 运行：node scripts/smoke-test.js
 * 覆盖：加载 jobs.json -> 渲染列表 -> 生成筛选选项 -> 校验首屏输出
 */
"use strict";

const fs = require("fs");
const path = require("path");

const WEB_DIR = path.resolve(__dirname, "..", "web");

function makeElement(tag) {
  const el = {
    tagName: tag.toUpperCase(),
    children: [],
    dataset: {},
    style: {},
    classList: { add() {}, remove() {}, toggle() {} },
    attributes: {},
    _listeners: {},
    innerHTML: "",
    value: "",
    textContent: "",
    parentElement: null,
    set innerHTMLCompat(v) {},
    addEventListener(type, fn) { (this._listeners[type] = this._listeners[type] || []).push(fn); },
    removeEventListener() {},
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
    querySelectorAll(sel) {
      const out = [];
      const walk = (n) => {
        for (const c of n.children) {
          const cls = (c.attributes.class || "").split(/\s+/).filter(Boolean);
          const tag = c.tagName.toLowerCase();
          const m = sel.match(/^([a-z]+)?(?:\.([\w-]+))?$/);
          if (m) {
            const t = m[1] || "*";
            const c2 = m[2];
            if ((t === "*" || t === tag) && (!c2 || cls.includes(c2))) out.push(c);
          }
          walk(c);
        }
      };
      walk(this);
      return out;
    },
    appendChild(c) { this.children.push(c); c.parentElement = this; return c; },
    removeChild(c) { this.children = this.children.filter((x) => x !== c); },
    setAttribute(k, v) { this.attributes[k] = String(v); },
    getAttribute(k) { return this.attributes[k]; },
    getBoundingClientRect() { return { top: 0, left: 0 }; },
    click() {},
  };
  Object.defineProperty(el, "innerHTML", {
    get() { return this._innerHTML || ""; },
    set(v) {
      this._innerHTML = v;
      this.children = [];
      // 解析简单的 <span data-key="x"> 与 <option value="v"> 片段
      const spanRe = /<span class="chip"[^>]*>[\s\S]*?<button data-key="([\w-]+)"/g;
      let m;
      while ((m = spanRe.exec(v))) {
        const b = makeElement("button");
        b.dataset.key = m[1];
        b.attributes.class = "chip";
        this.children.push(b);
      }
      const liRe = /<li class="job-card">/g;
      while (liRe.exec(v)) {
        this.children.push(makeElement("li"));
      }
      const optRe = /<option value="([^"]*)">/g;
      while ((m = optRe.exec(v))) {
        const o = makeElement("option");
        o.value = m[1];
        this.children.push(o);
      }
    },
  });
  return el;
}

const cache = new Map();
global.document = {
  getElementById(id) {
    if (!cache.has(id)) {
      const el = makeElement("div");
      el.id = id;
      cache.set(id, el);
    }
    const el = cache.get(id);
    el.parentElement = makeElement("div");
    return el;
  },
  querySelectorAll() { return []; },
  createElement: makeElement,
  body: makeElement("body"),
  addEventListener() {},
};
global.window = {
  L: {
    map() { return { setView() {}, eachLayer() {}, fitBounds() {}, invalidateSize() {}, addLayer() {}, removeLayer() {} }; },
    tileLayer() { return { addTo() {} }; },
    circleMarker() { return { addTo() {}, bindPopup() {}, on() {} }; },
    latLngBounds() { return {}; },
  },
  addEventListener() {},
};
global.fetch = (url) => {
  const file = path.join(WEB_DIR, url);
  return Promise.resolve({
    json: () => Promise.resolve(JSON.parse(fs.readFileSync(file, "utf-8"))),
  });
};
global.console = console;

const app = fs.readFileSync(path.join(WEB_DIR, "js", "app.js"), "utf-8");
eval(app);

// 等待异步加载完成后检查渲染结果
setTimeout(() => {
  const list = document.getElementById("job-list");
  const countEl = document.getElementById("stat-count");
  const chips = document.getElementById("active-chips");
  const filterSelects = ["f-province", "f-subject", "f-education", "f-level", "f-source", "f-days"]
    .map((id) => document.getElementById(id));
  const jobsRendered = list.children.length;
  console.log("统计显示:", countEl.textContent);
  console.log("列表渲染条数(首屏):", jobsRendered);
  console.log("筛选下拉选项数:", filterSelects.map((s) => s.children.length).join("/"));
  console.log("chips 数:", chips.children.length);
  if (jobsRendered <= 0 || !countEl.textContent.includes("共")) {
    console.error("渲染失败!");
    process.exit(1);
  }
  console.log("前端冒烟测试通过 ✅");
  process.exit(0);
}, 800);
