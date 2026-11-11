/* 验证前端 API 地址解析：请求必须跟随页面来源，换端口时不能死守 8765。
   做法：用不同的 location 桩真执行 index.html 的脚本，记录每个请求的 URL。 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ROOT = __dirname;
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const blocks = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  \u2713 ' + name); }
  else { fail++; console.log('  \u2717 ' + name + (detail ? '  \u2192 ' + detail : '')); }
}

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

function run({ protocol, origin, port, failSameOrigin }) {
  const els = {};
  const getEl = (id) => (els[id] || (els[id] = makeEl(id)));
  const store = new Map();
  const urls = [];

  const ctx = {
    console,
    localStorage: {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    },
    confirm: () => true, prompt: () => '', alert: () => {},
    setTimeout: () => 0, setInterval: () => 0, clearInterval: () => {},
    document: {
      getElementById: getEl,
      createElement: () => makeEl('new'),
      head: { appendChild() {} },
      addEventListener() {},
      body: makeEl('body'),
    },
    location: { protocol, origin, port, search: '', reload() {} },
    navigator: { userAgent: 'test' },
    URLSearchParams, Math, JSON, Date, Object, Array, String, Number, Boolean, Error, Promise,
    isNaN, parseFloat, parseInt, encodeURIComponent, decodeURIComponent,
  };
  ctx.window = ctx; ctx.globalThis = ctx;
  ctx.fetch = async (u) => {
    const s = String(u);
    urls.push(s);
    if (failSameOrigin && s.startsWith(origin)) throw new TypeError('Failed to fetch');
    return {
      ok: true, status: 200,
      json: async () => ({ lines: [], total: 0, connected: false, current: null,
                           busy: null, udid: null, ok: true }),
    };
  };

  const code = blocks.join('\n') + `\n;globalThis.__AB = () => API_BASE;
globalThis.__api = api;`;
  vm.createContext(ctx);
  vm.runInContext(code, ctx, { filename: 'index.html' });
  return { ctx, urls };
}

(async () => {
  /* ---- 场景 1：默认端口，页面与控制端同源 ---- */
  console.log('\n场景 1  访问 http://127.0.0.1:8765/');
  let r = run({ protocol: 'http:', origin: 'http://127.0.0.1:8765', port: '8765' });
  await r.ctx.__api('/api/status');
  check('请求打向页面同源地址',
    r.urls[r.urls.length - 1] === 'http://127.0.0.1:8765/api/status',
    '实际 ' + r.urls[r.urls.length - 1]);

  /* ---- 场景 2：非 8765 端口（比如 --port 9000）也不该硬编码 8765 ---- */
  console.log('\n场景 2  用 --port 9000 启动，访问 http://127.0.0.1:9000/');
  r = run({ protocol: 'http:', origin: 'http://127.0.0.1:9000', port: '9000' });
  await r.ctx.__api('/api/status');
  check('跟随页面端口，而不是死守 8765',
    r.urls[r.urls.length - 1] === 'http://127.0.0.1:9000/api/status',
    '实际 ' + r.urls[r.urls.length - 1]);

  /* ---- 场景 3：页面由别的端口托管，同源不可达则回退本机 8765 ---- */
  console.log('\n场景 3  页面由 9000 端口托管，控制端在 8765');
  r = run({ protocol: 'http:', origin: 'http://127.0.0.1:9000', port: '9000',
            failSameOrigin: true });
  try {
    await r.ctx.__api('/api/status');
  } catch (e) {
    console.log('    [诊断] 抛出：' + e.message);
    console.log('    [诊断] 请求序列：' + JSON.stringify(r.urls));
    console.log('    [诊断] 当前 API_BASE：' + r.ctx.__AB());
  }
  check('同源失败后自动回退到 127.0.0.1:8765',
    r.urls.some(u => u === 'http://127.0.0.1:8765/api/status'),
    '实际 ' + JSON.stringify(r.urls));
  check('回退后地址被记住，不再重复失败',
    r.ctx.__AB() === 'http://127.0.0.1:8765', '实际 ' + r.ctx.__AB());

  /* ---- 场景 4：本地文件打开（无 http 源） ---- */
  console.log('\n场景 4  用 file:// 打开页面');
  r = run({ protocol: 'file:', origin: 'null', port: '' });
  check('直接指向本机 8765', r.ctx.__AB() === 'http://127.0.0.1:8765',
    '实际 ' + r.ctx.__AB());

  console.log('\n' + '='.repeat(56));
  console.log(`通过 ${pass} 项，失败 ${fail} 项`);
  process.exit(fail ? 1 : 0);
})();
