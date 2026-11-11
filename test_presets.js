/* 用 DOM/localStorage 桩，真实执行 index.html 里的前端代码，验证「常用地点」增删逻辑 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = __dirname;
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);

/* ---------- 桩 ---------- */
function makeEl(id) {
  const el = {
    id, className: '', textContent: '', title: '',
    style: {}, children: [], disabled: false, value: '', checked: true,
    appendChild(c) { this.children.push(c); return c; },
    addEventListener() {}, setAttribute() {}, removeAttribute() {},
    querySelector() { return null; },
  };
  // innerHTML 赋值要真的清空子节点，否则多次 renderChips 会累加（桩子必须仿真这一点）
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
const localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
let confirmAnswer = true;
const logs = [];

const ctx = {
  console,
  localStorage,
  confirm: () => confirmAnswer,
  prompt: () => '测试点',
  alert: () => {},
  fetch: () => Promise.reject(new Error('no network in test')),
  setTimeout: () => 0,
  setInterval: () => 0,
  clearInterval: () => {},
  document: {
    getElementById: getEl,
    createElement: () => makeEl('new'),
    head: { appendChild() {}, },
    addEventListener() {},
  },
  location: { port: '8765', origin: 'http://127.0.0.1:8765', search: '', reload() {} },
  URLSearchParams,
  Math, JSON, Date, Object, Array, String, Number, Boolean, Error, Promise,
};
ctx.window = ctx;
ctx.globalThis = ctx;
vm.createContext(ctx);

/* 执行 + 导出内部函数 */
const code = blocks.join('\n') + `\n;globalThis.__T = { allPresets, renderChips, removePreset,
  loadCustom, saveCustom, loadHidden, saveHidden, BUILTIN, removePreset };`;
try { vm.runInContext(code, ctx, { filename: 'index.html' }); }
catch (e) { console.log('执行失败:', e.message); process.exit(1); }

const T = ctx.__T;
let pass = 0, fail = 0;
function check(desc, cond, extra) {
  if (cond) { pass++; console.log(`  ✓ ${desc}`); }
  else { fail++; console.log(`  ✗ ${desc}${extra ? '  → ' + extra : ''}`); }
}

console.log('「常用地点」增删逻辑验证');
console.log('='.repeat(56));

// 1 初始状态
check('初始内置点 = 10 个', T.BUILTIN.length === 10, `实际 ${T.BUILTIN.length}`);
check('初始自定义点 = 0 个', T.loadCustom().length === 0);
check('初始展示 = 10 个', T.allPresets().length === 10, `实际 ${T.allPresets().length}`);

// 2 模拟用户保存了一个自定义点（如「卢森堡中心」）
T.saveCustom([['卢森堡中心', 34.79, 113.72]]);
check('保存自定义点后 = 11 个', T.allPresets().length === 11, `实际 ${T.allPresets().length}`);

// 3 删除自定义点（用户的核心诉求）
confirmAnswer = true;
T.removePreset('卢森堡中心', true);
check('删除「卢森堡中心」后 = 10 个', T.allPresets().length === 10, `实际 ${T.allPresets().length}`);
check('自定义存储已清空', T.loadCustom().length === 0);
check('内置点未受影响', T.allPresets().some(p => p[0] === '郑州·二七广场'));

// 4 取消确认时不应删除
T.saveCustom([['临时点', 1, 2]]);
confirmAnswer = false;
T.removePreset('临时点', true);
check('confirm 取消 → 不删除', T.allPresets().length === 11, `实际 ${T.allPresets().length}`);
confirmAnswer = true;
T.removePreset('临时点', true);
check('再次删除成功', T.allPresets().length === 10);

// 5 删除内置点 = 隐藏，且可恢复
T.removePreset('纽约·自由女神', false);
check('隐藏内置点后 = 9 个', T.allPresets().length === 9, `实际 ${T.allPresets().length}`);
check('内置 BUILTIN 本身未被改动', T.BUILTIN.length === 10);

// 6 渲染出的 chip 数量与 × 按钮
T.renderChips();
const chips = getEl('chips').children;
check('渲染 chip 数 = 9', chips.length === 9, `实际 ${chips.length}`);
check('每个 chip 都带 × 删除钮',
  chips.every(c => c.children.some(k => k.className === 'x')));
check('chip 有 title 提示',
  chips.every(c => (c.title || '').includes('点击下发定位')));

// 7 自建点重名覆盖（不产生重复）
T.saveCustom([['重复点', 10, 20]]);
T.saveCustom([['重复点', 30, 40]]);
check('同名保存不产生重复项', T.loadCustom().length === 1, `实际 ${T.loadCustom().length}`);
check('同名保存取最新坐标', T.loadCustom()[0][1] === 30);
T.saveCustom([]);

// 8 恢复默认
localStorage.removeItem('iosloc.presets');
localStorage.removeItem('iosloc.hidden');
check('恢复默认后 = 10 个', T.allPresets().length === 10, `实际 ${T.allPresets().length}`);
T.renderChips();
check('恢复默认后渲染 10 个 chip', getEl('chips').children.length === 10,
  `实际 ${getEl('chips').children.length}`);

console.log('='.repeat(56));
console.log(`通过 ${pass} 项，失败 ${fail} 项`);
process.exit(fail ? 1 : 0);
