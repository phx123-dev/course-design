/* 前端挂载测试: jsdom 加载真实 vue/element-plus 库与全部页面组件,
 * ECharts/axios 打桩, 逐页挂载断言关键元素渲染且无运行时异常。
 * 运行: cd tests && npm install && node frontend_mount_test.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { JSDOM } = require('jsdom');

const ROOT = path.resolve(__dirname, '..');
const FRONTEND = path.join(ROOT, 'frontend');
const PASS = [];
const FAIL = [];

function check(name, cond, detail = '') {
  if (cond) { PASS.push(name); console.log(`  [PASS] ${name}`); }
  else { FAIL.push(name); console.log(`  [FAIL] ${name} ${detail}`); }
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

/* ---------- axios 桩 ---------- */
function makeAxios() {
  const ax = {
    get: async () => { throw new Error('no mock for GET'); },
    post: async () => { throw new Error('no mock for POST'); },
    put: async () => { throw new Error('no mock for PUT'); },
    delete: async () => { throw new Error('no mock for DELETE'); },
    interceptors: { request: { use() {} }, response: { use() {} } },
  };
  ax.get = async (url) => {
    if (url === '/api/auth/me') return { data: { code: 0, data: { id: 1, username: 'admin', role: 'admin', display_name: '系统管理员' } } };
    if (url === '/api/health') return { data: { code: 0, data: { status: 'ok', llm_mode: 'offline' } } };
    if (url === '/api/devices') return { data: { code: 0, data: [
      { id: 1, code: 'EQ-001', name: '数控车床 CK6140 主轴轴承', etype: '数控机床', location: '一号车间 A区', rpm: 1750, load_ratio: 0.8, health_state: 0, status: '运行', description: '' },
      { id: 2, code: 'EQ-002', name: '立式加工中心 VMC850 主轴轴承', etype: '数控机床', location: '一号车间 A区', rpm: 2200, load_ratio: 0.8, health_state: 2, status: '运行', description: '' },
    ] } };
    if (url === '/api/dashboard/overview') return { data: { code: 0, data: {
      stats: { device_total: 2, device_running: 2, device_healthy: 1, device_fault: 1, active_alarms: 0, pending_workorders: 0, stream_running: true },
      health_dist: [{ name: '正常', value: 1 }, { name: '内圈故障', value: 0 }, { name: '外圈故障', value: 1 }, { name: '滚动体故障', value: 0 }],
      alarms_trend: Array.from({ length: 24 }, (_, i) => ({ hour: i + ':00', count: 0 })),
      device_list: [],
      recent_alarms: [],
    } } };
    if (url === '/api/monitoring/realtime') return { data: { code: 0, data: [] } };
    if (url.startsWith('/api/alarms')) return { data: { code: 0, data: [] } };
    if (url.startsWith('/api/devices/')) return { data: { code: 0, data: { id: 1, code: 'EQ-001', name: '数控车床 CK6140 主轴轴承', health_state: 0, rpm: 1750, load_ratio: 0.8, location: '一号车间 A区', status: '运行' } } };
    throw new Error('unexpected GET ' + url);
  };
  return ax;
}

/* ---------- ECharts 桩 ---------- */
function makeEcharts() {
  return { init: () => ({ setOption() {}, resize() {}, dispose() {}, getDom() { return null; } }) };
}

/* 在 jsdom 窗口中执行前端脚本 */
function runFrontend(dom) {
  const code = [
    { file: path.join(FRONTEND, 'libs', 'vue.min.js') },
    { file: path.join(FRONTEND, 'libs', 'element-plus.min.js') },
    { file: path.join(FRONTEND, 'libs', 'echarts.min.js'), stub: true },
    { file: path.join(FRONTEND, 'libs', 'axios.min.js'), stub: true },
    { file: path.join(FRONTEND, 'assets', 'components.js') },
    { file: path.join(FRONTEND, 'assets', 'pages2.js') },
    { file: path.join(FRONTEND, 'assets', 'app.js') },
  ];
  for (const { file, stub } of code) {
    const src = fs.readFileSync(file, 'utf-8');
    vm.runInContext(src, dom.getInternalVMContext(), { filename: file });
    if (stub) {
      // 库加载后立刻用桩替换全局对象（axios/echarts）
      const name = file.includes('echarts') ? 'echarts' : 'axios';
      vm.runInContext(
        `${name} = ${name === 'axios' ? '(__stub_axios__)' : '(__stub_echarts__)'};`,
        dom.getInternalVMContext()
      );
    }
  }
}

async function mountPage(page) {
  const html = fs.readFileSync(path.join(FRONTEND, 'index.html'), 'utf-8');
  const dom = new JSDOM(html, {
    url: 'http://localhost:8000/',
    runScripts: 'outside-only',
    pretendToBeVisual: true,
  });
  const ctx = dom.getInternalVMContext();
  ctx.__stub_axios__ = makeAxios();
  ctx.__stub_echarts__ = makeEcharts();
  ctx.console = console;
  ctx.ElMessage = { success() {}, error() {}, warning() {} };
  ctx.ElMessageBox = { confirm: async () => {} };
  ctx.localStorage.setItem('phx_token', 'test-token');   // 已登录
  ctx.onerror = (msg) => { FAIL.push('页面运行时异常: ' + msg); console.log('  [FAIL] JS 异常: ' + msg); };
  runFrontend(dom);
  await sleep(120);
  const doc = dom.window.document;
  return { dom, doc };
}

(async () => {
  console.log('== 前端挂载测试（jsdom + 真实 Vue/ElementPlus 库）==\n');

  const { dom, doc } = await mountPage('dashboard');
  check('根组件挂载 #app', !!doc.querySelector('#app .layout'), '#app 未渲染 layout');
  check('侧边栏菜单渲染', doc.querySelectorAll('.sidebar .el-menu-item').length >= 6,
    '菜单项数量=' + doc.querySelectorAll('.sidebar .el-menu-item').length);
  check('管理员可见系统管理菜单', doc.querySelectorAll('.sidebar .el-menu-item').length === 7,
    'admin 角色应显示 7 个菜单项');
  check('默认页面为健康看板', !!doc.querySelector('.main') && doc.body.textContent.includes('设备健康一览'));

  // 逐页切换挂载并断言页面内容（jsdom 中直接驱动 Vue 实例，绕过菜单 DOM 事件）
  const pages = [
    { page: 'monitoring', menu: '设备监控', expect: '请选择设备开始监控' },
    { page: 'chat', menu: '智能诊断', expect: '智能诊断对话建设中' },
    { page: 'workorders', menu: '工单管理', expect: '工单管理建设中' },
    { page: 'knowledge', menu: '知识库', expect: '知识库管理建设中' },
    { page: 'devices', menu: '设备台账', expect: '共 2 台' },
    { page: 'admin', menu: '系统管理', expect: '系统说明' },
  ];
  for (const p of pages) {
    check(`菜单项「${p.menu}」存在`,
      [...doc.querySelectorAll('.el-menu-item')].some(e => e.textContent.includes(p.menu)));
    dom.window.appRoot.switchPage(p.page);
    await sleep(60);
    check(`页面「${p.menu}」挂载`, doc.body.textContent.includes(p.expect),
      '未找到: ' + p.expect);
  }

  console.log(`\n== 结果: ${PASS.length} PASS / ${FAIL.length} FAIL ==`);
  process.exit(FAIL.length ? 1 : 0);
})();
