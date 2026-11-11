/* 复现「保存当前坐标后，点该坐标跳到别处」的问题
   做法：用 DOM 桩真执行 index.html 的前端代码，捕获每次下发给控制端的坐标。 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = __dirname;
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);

function makeEl(id) {
  const el = {
    id, className: '', textContent: '', title: '', style: {}, children: [],
    disabled: false, value: '', checked: false,
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {}, setAttribute() {}, removeAttribute() {}, querySelector: () => null,
  };
  let _html = '';
  Object.defineProperty(el, 'innerHTML', {
    get() { return _html; },
    set(v) { _html = v; if (v === '') el.children.length = 0; },
    enumerable: true,
  });
  return el;
}
const els = {};
const getEl = (id) => (els[id] || (els[id] = makeEl(id)));

const store = new Map();
let promptAnswer = '';
let statusPayload = { connected: false, current: null, busy: null, udid: null };
const dispatched = [];   // 每次下发给控制端的坐标

const ctx = {
  console, localStorage: {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  },
  confirm: () => true,
  prompt: () => promptAnswer,
  alert: () => {},
  setTimeout: () => 0, setInterval: () => 0, clearInterval: () => {},
  document: {
    getElementById: getEl,
    createElement: () => makeEl('new'),
    head: { appendChild() {} },
    addEventListener() {},
  },
  location: { port: '8765', origin: 'http://127.0.0.1:8765', search: '', reload() {} },
  URLSearchParams, Math, JSON, Date, Object, Array, String, Number, Boolean, Error, Promise,
};
ctx.window = ctx; ctx.globalThis = ctx;
ctx.fetch = async (url, opt = {}) => {
  const u = String(url);
  if (u.includes('/api/location')) {
    dispatched.push(JSON.parse(opt.body));
    return { ok: true, status: 200, json: async () => ({ ok: true }) };
  }
  if (u.includes('/api/status')) return { ok: true, status: 200, json: async () => statusPayload };
  if (u.includes('/api/log')) return { ok: true, status: 200, json: async () => ({ lines: [] }) };
  return { ok: true, status: 200, json: async () => ({ ok: true }) };
};
vm.createContext(ctx);

const code = blocks.join('\n') + `\n;globalThis.__T = { place, doSet, wgs2gcj, gcj2wgs, refreshStatus,
  loadCustom, allPresets, renderChips, saveCustom };
globalThis.__h = { set: document.getElementById('btn-set').onclick,
                   save: document.getElementById('btn-save').onclick };`
  ;
vm.runInContext(code, ctx, { filename: 'index.html' });
const T = ctx.__T;

const flush = async (n = 30) => { for (let i = 0; i < n; i++) await Promise.resolve(); };
// 真实页面每 2 秒轮询一次状态；测试里显式调一次，模拟"轮询已发生"
const syncStatus = async () => { await T.refreshStatus(); await flush(); };
const last = () => dispatched[dispatched.length - 1];
const near = (a, b, tol = 1e-6) => Math.abs(a - b) < tol;

let pass = 0, fail = 0;
const check = (d, c, extra) => {
  if (c) { pass++; console.log(`  ✓ ${d}`); }
  else { fail++; console.log(`  ✗ ${d}${extra ? '  → ' + extra : ''}`); }
};
const reset = () => {
  store.clear(); dispatched.length = 0;
  getEl('chips').children.length = 0;
  getEl('in-lat').value = ''; getEl('in-lon').value = '';
  T.renderChips();
};

/* 模拟"在地图上点一下"：地图给的是 GCJ-02，place() 内部转 WGS-84 */
function clickMap(lat, lon) {
  const g = T.wgs2gcj(lon, lat);       // [glng, glat]
  T.place(g[1], g[0], getEl('chk-auto').checked);
}
function clickChip(name) {
  const chip = getEl('chips').children.find(c => c.children[0].textContent === name);
  if (!chip) return false;
  chip.children[0].onclick();
  return true;
}

(async () => {
  /* ---- 场景 1：地图点A → 保存A → 点A ---- */
  reset();
  clickMap(34.794605, 113.727719);            // 龙湖国际中心北楼
  promptAnswer = 'A-龙湖';
  ctx.__h.save();
  await flush();
  dispatched.length = 0;
  check('场景1 保存后能在列表里找到 A-龙湖', clickChip('A-龙湖'));
  await flush();
  check('场景1 点 A-龙湖 → 下发到原坐标',
    last() && near(last().lat, 34.794605) && near(last().lon, 113.727719),
    JSON.stringify(last()));

  /* ---- 场景 2：地图点A → 手输B → 下发 → 保存B → 点B ---- */
  reset();
  clickMap(34.794605, 113.727719);            // 先在地图上点了 A
  getEl('in-lat').value = '34.752849';        // 再手动改到 B（二七广场）
  getEl('in-lon').value = '113.659807';
  ctx.__h.set();                              // 点「下发定位」
  await flush();
  promptAnswer = 'B-二七广场';
  ctx.__h.save();                             // 点「保存当前」
  await flush();
  dispatched.length = 0;
  check('场景2 保存后能在列表里找到 B-二七广场', clickChip('B-二七广场'));
  await flush();
  check('场景2 点 B-二七广场 → 下发到 B（手动输入的坐标）',
    last() && near(last().lat, 34.752849, 1e-5) && near(last().lon, 113.659807, 1e-5),
    JSON.stringify(last()));

  /* ---- 场景 3：什么都没点就保存，不应写入 ---- */
  reset();
  statusPayload = { connected: false, current: null, busy: null, udid: null };
  await syncStatus();
  promptAnswer = 'C-幽灵点';
  ctx.__h.save();
  await flush();
  check('场景3 无当前坐标时保存 → 不产生地点', !clickChip('C-幽灵点'));

  /* ---- 场景 4：控制端正在模拟某点，保存的应是服务端真实当前点 ---- */
  reset();
  statusPayload = { connected: true, current: { lat: 22.546373, lon: 114.054522 }, busy: null, udid: 'x' };
  getEl('in-lat').value = ''; getEl('in-lon').value = '';   // 界面输入框为空
  await syncStatus();                                       // 模拟状态轮询已发生
  promptAnswer = 'D-服务端点';
  ctx.__h.save();
  await flush();
  dispatched.length = 0;
  check('场景4 保存后能在列表里找到 D-服务端点', clickChip('D-服务端点'));
  await flush();
  check('场景4 点 D-服务端点 → 下发到服务端当前点',
    last() && near(last().lat, 22.546373, 1e-5) && near(last().lon, 114.054522, 1e-5),
    JSON.stringify(last()));

  console.log(`\n通过 ${pass} 项，失败 ${fail} 项`);
  process.exit(fail ? 1 : 0);
})();
