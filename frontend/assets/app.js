/* 根应用：页面切换 + 登录态 + axios 封装（含 401 自动跳登录） */
'use strict';

/* 请求封装：统一解包 response.data，自动携带令牌，401 自动登出 */
const api = {
  get: async (url, params) => (await axios.get(url, { params })).data,
  post: async (url, data) => (await axios.post(url, data)).data,
  put: async (url, data) => (await axios.put(url, data)).data,
  del: async (url) => (await axios.delete(url)).data,
};

axios.interceptors.request.use(cfg => {
  const t = localStorage.getItem('phx_token');
  if (t) cfg.headers.Authorization = 'Bearer ' + t;
  return cfg;
});
axios.interceptors.response.use(
  r => r,
  err => {
    if (err.response && err.response.status === 401 && !location.hash.includes('login')) {
      localStorage.removeItem('phx_token');
      location.reload();   // 回到登录页
    }
    return Promise.reject(err);
  }
);

const ROLE_NAMES = { admin: '系统管理员', engineer: '维护工程师', manager: '车间管理员' };
const PAGE_TITLES = {
  dashboard: '设备健康总览看板', monitoring: '设备实时监控', chat: '智能诊断对话',
  workorders: '维护工单管理', knowledge: '知识库管理', devices: '设备台账',
  admin: '系统管理',
};

const App = {
  data() {
    return {
      page: 'dashboard',
      user: null,                 // 当前用户（null = 未登录）
      llmMode: 'offline',         // 系统当前运行模式（顶部标签）
      loginForm: { username: '', password: '' },
      loggingIn: false,
      pageProps: {},              // 跨页跳转上下文
    };
  },
  computed: {
    pageTitle() { return PAGE_TITLES[this.page] || ''; },
    roleName() { return this.user ? (ROLE_NAMES[this.user.role] || this.user.role) : ''; },
  },
  methods: {
    async doLogin() {
      if (!this.loginForm.username || !this.loginForm.password) {
        return ElMessage.warning('请输入用户名和密码');
      }
      this.loggingIn = true;
      try {
        const res = await api.post('/api/auth/login', this.loginForm);
        localStorage.setItem('phx_token', res.data.token);
        this.user = res.data.user;
        this.page = 'dashboard';
        this.refreshLlmMode();
        ElMessage.success(`欢迎，${this.user.display_name || this.user.username}`);
      } catch (e) {
        ElMessage.error(e.response?.data?.detail || '登录失败');
      } finally {
        this.loggingIn = false;
      }
    },
    async doLogout() {
      try { await api.post('/api/auth/logout'); } catch (e) { /* 忽略 */ }
      localStorage.removeItem('phx_token');
      this.user = null;
    },
    /* 页面切换；ctx 为跨页上下文（如从看板跳转监控指定设备） */
    switchPage(p, ctx) {
      this.page = p;
      this.pageProps = ctx || {};
    },
    async refreshLlmMode() {
      try {
        const res = await api.get('/api/health');
        this.llmMode = res.data.llm_mode;
      } catch (e) { this.llmMode = 'offline'; }
    },
  },
  async mounted() {
    const t = localStorage.getItem('phx_token');
    if (!t) return;
    try {
      const res = await api.get('/api/auth/me');
      this.user = res.data;
    } catch (e) {
      localStorage.removeItem('phx_token');
    }
    this.refreshLlmMode();
  },
};

const app = Vue.createApp(App);
app.use(ElementPlus);
app.config.globalProperties.$ELEMENT = { size: 'small' };

/* 公共组件（components.js）与页面组件（pages2.js）统一注册为 kebab-case */
function toKebab(name) {
  return name.replace(/([A-Z])/g, '-$1').toLowerCase().replace(/^-/, '');
}
for (const [name, comp] of Object.entries(window.Components || {})) {
  app.component(toKebab(name), comp);
}
for (const [name, comp] of Object.entries(window.Pages || {})) {
  app.component('page-' + toKebab(name), comp);
}

const appRoot = app.mount('#app');
window.appRoot = appRoot;
