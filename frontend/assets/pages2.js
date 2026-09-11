/* 页面组件库（按里程碑逐步实现；M4：设备台账 + 系统管理框架） */
'use strict';
window.Pages = window.Pages || {};

/* ============ 设备台账（F2）============ */
window.Pages.Devices = {
  data() {
    return {
      list: [], loading: false,
      dialog: false, editing: null,
      form: this.emptyForm(),
    };
  },
  template: `
  <div>
    <div class="panel">
      <div class="panel-title">
        <span>设备台账（共 {{ list.length }} 台）</span>
        <div>
          <el-button type="primary" :disabled="!isAdmin" @click="openCreate">＋ 新增设备</el-button>
          <el-button @click="load">刷新</el-button>
        </div>
      </div>
      <el-table :data="list" v-loading="loading" border stripe size="small">
        <el-table-column prop="code" label="编号" width="90" />
        <el-table-column prop="name" label="设备名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="etype" label="类型" width="100" />
        <el-table-column prop="location" label="位置" width="130" show-overflow-tooltip />
        <el-table-column prop="rpm" label="转速(rpm)" width="95" />
        <el-table-column prop="load_ratio" label="负载率" width="80">
          <template #default="{row}">{{ (row.load_ratio*100).toFixed(0) }}%</template>
        </el-table-column>
        <el-table-column label="健康状态" width="110">
          <template #default="{row}"><health-tag :state="row.health_state" /></template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="70" />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{row}">
            <el-button link type="primary" :disabled="!isAdmin" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" :disabled="!isAdmin" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialog" :title="editing ? '编辑设备' : '新增设备'" width="560px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="设备编号"><el-input v-model="form.code" :disabled="!!editing" /></el-form-item>
        <el-form-item label="设备名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="设备类型">
          <el-select v-model="form.etype" style="width:100%">
            <el-option v-for="t in ['数控机床','风机','电机','旋转机械']" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="安装位置"><el-input v-model="form.location" /></el-form-item>
        <el-form-item label="投用日期"><el-input v-model="form.commission_date" placeholder="如 2025-06-01" /></el-form-item>
        <el-form-item label="额定转速"><el-input-number v-model="form.rpm" :min="100" :max="20000" :step="50" /></el-form-item>
        <el-form-item label="负载率"><el-input-number v-model="form.load_ratio" :min="0" :max="1.2" :step="0.05" /></el-form-item>
        <el-form-item label="健康状态">
          <el-select v-model="form.health_state" style="width:100%">
            <el-option :value="0" label="正常" />
            <el-option :value="1" label="内圈故障" />
            <el-option :value="2" label="外圈故障" />
            <el-option :value="3" label="滚动体故障" />
          </el-select>
        </el-form-item>
        <el-form-item label="运行状态">
          <el-radio-group v-model="form.status"><el-radio value="运行">运行</el-radio><el-radio value="停机">停机</el-radio></el-radio-group>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog=false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>`,
  computed: { isAdmin() { return this.$root.user && this.$root.user.role === 'admin'; } },
  methods: {
    emptyForm() {
      return { code: '', name: '', etype: '旋转机械', location: '', commission_date: '',
               rpm: 1750, load_ratio: 0.8, health_state: 0, status: '运行', description: '' };
    },
    async load() {
      this.loading = true;
      try {
        const res = await api.get('/api/devices');
        this.list = res.data;
      } catch (e) { ElMessage.error('加载失败'); }
      this.loading = false;
    },
    openCreate() { this.editing = null; this.form = this.emptyForm(); this.dialog = true; },
    openEdit(row) {
      this.editing = row;
      this.form = { ...row };
      this.dialog = true;
    },
    async save() {
      try {
        if (this.editing) await api.put('/api/devices/' + this.editing.id, this.form);
        else await api.post('/api/devices', this.form);
        ElMessage.success('保存成功');
        this.dialog = false;
        this.load();
      } catch (e) { ElMessage.error(e.response?.data?.detail || '保存失败'); }
    },
    async remove(row) {
      await ElMessageBox.confirm(`确认删除设备 ${row.code}？`, '提示', { type: 'warning' });
      try {
        await api.del('/api/devices/' + row.id);
        ElMessage.success('已删除');
        this.load();
      } catch (e) { ElMessage.error(e.response?.data?.detail || '删除失败'); }
    },
  },
  mounted() { this.load(); },
};

/* ============ 系统管理（框架；后续里程碑补充用户/数据源配置） ============ */
window.Pages.Admin = {
  data() { return { info: {} }; },
  template: `
  <div>
    <div class="stat-row">
      <div class="stat-card"><div class="stat-num">{{ info.llm_mode === 'llm' ? 'LLM 在线' : '离线模拟' }}</div><div class="stat-label">智能层运行模式</div></div>
      <div class="stat-card"><div class="stat-num">{{ info.db_size || '-' }}</div><div class="stat-label">数据库</div></div>
    </div>
    <div class="panel">
      <div class="panel-title"><span>系统说明</span></div>
      <p style="font-size:13px;color:#606266;line-height:1.9">
        1. 大模型配置：项目根目录 .env 文件（DEEPSEEK_API_KEY），无 Key 时系统自动进入离线模拟模式，全部功能可用。<br/>
        2. 数据源：设备实时数据由内置模拟信号生成器提供（按轴承特征频率 BPFI/BPFO/BSF 合成），波形可确定性回放。<br/>
        3. 角色权限：维护工程师（监控/诊断/工单执行）、车间管理员（看板/报表/工单审批）、系统管理员（台账/知识库/配置）。
      </p>
    </div>
  </div>`,
  async mounted() {
    try {
      const res = await api.get('/api/health');
      this.info.llm_mode = res.data.llm_mode;
    } catch (e) { /* 忽略 */ }
  },
};

/* ============ 健康看板（F3） ============ */
window.Pages.Dashboard = {
  data() {
    return {
      loading: false,
      stats: {}, healthDist: [], alarmsTrend: [], deviceList: [], recentAlarms: [],
      timer: null, charts: {},
    };
  },
  template: `
  <div v-loading="loading">
    <div class="stat-row">
      <div class="stat-card"><div class="stat-num">{{ stats.device_total || 0 }}</div><div class="stat-label">设备总数</div></div>
      <div class="stat-card"><div class="stat-num">{{ stats.device_running || 0 }}</div><div class="stat-label">运行中</div></div>
      <div class="stat-card"><div class="stat-num tag-good">{{ stats.device_healthy || 0 }}</div><div class="stat-label">健康设备</div></div>
      <div class="stat-card"><div class="stat-num tag-danger">{{ stats.device_fault || 0 }}</div><div class="stat-label">故障设备</div></div>
      <div class="stat-card"><div class="stat-num tag-warn">{{ stats.active_alarms || 0 }}</div><div class="stat-label">活跃预警</div></div>
      <div class="stat-card"><div class="stat-num">{{ stats.pending_workorders || 0 }}</div><div class="stat-label">待处理工单</div></div>
    </div>

    <el-row :gutter="14">
      <el-col :span="10">
        <div class="panel">
          <div class="panel-title"><span>设备健康分布</span><span class="sub" v-if="stats.stream_running">📡 数据流运行中</span></div>
          <div ref="pieChart" class="chart-box" style="height:260px"></div>
        </div>
      </el-col>
      <el-col :span="14">
        <div class="panel">
          <div class="panel-title"><span>近 24 小时预警趋势</span></div>
          <div ref="trendChart" class="chart-box" style="height:260px"></div>
        </div>
      </el-col>
    </el-row>

    <div class="panel">
      <div class="panel-title"><span>设备健康一览</span><span class="sub">点击行跳转设备监控</span></div>
      <el-table :data="deviceList" border stripe size="small">
        <el-table-column prop="code" label="编号" width="90" />
        <el-table-column prop="name" label="设备名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="健康状态" width="110">
          <template #default="{row}"><health-tag :state="row.health_state" /></template>
        </el-table-column>
        <el-table-column label="实时 RMS" width="100">
          <template #default="{row}">
            <span v-if="row.last_sample">{{ row.last_sample.rms }}</span>
            <span v-else style="color:#c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="实时温度" width="100">
          <template #default="{row}">
            <span v-if="row.last_sample">{{ row.last_sample.temp }}℃</span>
            <span v-else style="color:#c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="健康评分" width="100">
          <template #default="{row}">
            <span v-if="row.last_prediction">{{ row.last_prediction.health_score.toFixed(0) }}</span>
            <span v-else style="color:#c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="最新预警" min-width="220">
          <template #default="{row}">
            <span v-for="a in recentAlarms.filter(x=>x.device_id===row.id).slice(0,1)" :key="a.id"
                  style="color:#e6a23c;font-size:12px">{{ a.message }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{row}">
            <el-button link type="primary" @click="gotoMonitor(row)">监控</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>`,
  methods: {
    async load() {
      this.loading = true;
      try {
        const res = await api.get('/api/dashboard/overview');
        Object.assign(this, {
          stats: res.data.stats, healthDist: res.data.health_dist,
          alarmsTrend: res.data.alarms_trend, deviceList: res.data.device_list,
          recentAlarms: res.data.recent_alarms,
        });
        this.renderCharts();
      } catch (e) { /* 忽略 */ }
      this.loading = false;
    },
    renderCharts() {
      const pie = this.charts.pie || (this.charts.pie = echarts.init(this.$refs.pieChart));
      pie.setOption({
        tooltip: { trigger: 'item' },
        legend: { bottom: 0 },
        color: ['#67c23a', '#f56c6c', '#e6a23c', '#f78989'],
        series: [{
          type: 'pie', radius: ['40%', '65%'], center: ['50%', '45%'],
          label: { formatter: '{b}: {c}' },
          data: this.healthDist,
        }],
      });
      const trend = this.charts.trend || (this.charts.trend = echarts.init(this.$refs.trendChart));
      trend.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 40, right: 16, top: 20, bottom: 28 },
        xAxis: { type: 'category', data: this.alarmsTrend.map(t => t.hour), axisLabel: { fontSize: 10 } },
        yAxis: { type: 'value', minInterval: 1 },
        series: [{
          type: 'bar', data: this.alarmsTrend.map(t => t.count),
          itemStyle: { color: '#e6a23c' }, barWidth: 10,
        }],
      });
    },
    gotoMonitor(row) {
      this.$root.switchPage('monitoring', { device_id: row.id });
    },
    onResize() { Object.values(this.charts).forEach(c => c.resize()); },
  },
  mounted() {
    this.load();
    this.timer = setInterval(this.load, 5000);       // 5s 自动刷新
    window.addEventListener('resize', this.onResize);
  },
  beforeUnmount() {
    clearInterval(this.timer);
    window.removeEventListener('resize', this.onResize);
    Object.values(this.charts).forEach(c => c.dispose());
  },
};

/* ============ 设备实时监控（F3） ============ */
window.Pages.Monitoring = {
  props: { device_id: { type: Number, default: null } },
  data() {
    return {
      deviceId: this.device_id || null,
      device: null,
      rmsBuffer: [], tempBuffer: [],      // 最近 120 点实时曲线
      waveform: null,
      alarms: [],
      prediction: null, predicting: false,
      rulDemo: null, rulLoading: false,
      ws: null, wsConnected: false, pollTimer: null, waveTimer: null,
      charts: {},
    };
  },
  template: `
  <div>
    <div class="panel">
      <div class="panel-title">
        <span>设备选择与状态</span>
      </div>
      <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
        <device-select v-model="deviceId" placeholder="选择要监控的设备" style="width:340px" />
        <template v-if="device">
          <health-tag :state="device.health_state" />
          <span style="font-size:13px;color:#606266">{{ device.name }} · {{ device.location }}</span>
          <span style="font-size:13px;color:#909399">转速 {{ device.rpm }} rpm · 负载 {{ (device.load_ratio*100).toFixed(0) }}%</span>
        </template>
        <span style="margin-left:auto;font-size:12px;color:#909399">
          连接：<span :style="{color: wsConnected ? '#67c23a' : '#e6a23c'}">{{ wsConnected ? 'WebSocket 实时' : '轮询兜底' }}</span>
        </span>
      </div>
    </div>

    <div v-if="!deviceId" class="panel" style="text-align:center;color:#909399;padding:40px">
      请选择设备开始监控
    </div>
    <template v-else>
      <el-row :gutter="14">
        <el-col :span="12">
          <div class="panel">
            <div class="panel-title"><span>振动 RMS 趋势（最近 120 秒）</span></div>
            <div ref="rmsChart" class="chart-box"></div>
          </div>
        </el-col>
        <el-col :span="12">
          <div class="panel">
            <div class="panel-title"><span>轴承温度趋势</span></div>
            <div ref="tempChart" class="chart-box"></div>
          </div>
        </el-col>
      </el-row>

      <el-row :gutter="14">
        <el-col :span="14">
          <div class="panel">
            <div class="panel-title">
              <span>振动波形与频谱（确定性回放）</span>
              <span class="sub">特征频率：BPFI {{ charFreqs.bpfi || '-' }} / BPFO {{ charFreqs.bpfo || '-' }} / BSF {{ charFreqs.bsf || '-' }} Hz</span>
            </div>
            <div ref="waveChart" class="chart-box" style="height:220px"></div>
          </div>
        </el-col>
        <el-col :span="10">
          <div class="panel">
            <div class="panel-title"><span>演示控制：故障注入</span></div>
            <div style="display:flex;flex-direction:column;gap:10px">
              <el-button type="success" @click="inject(0)">✅ 恢复正常</el-button>
              <el-button type="warning" @click="inject(2)">⚠️ 注入外圈故障</el-button>
              <el-button type="danger" @click="inject(1)">🔴 注入内圈故障</el-button>
              <el-button type="danger" @click="inject(3)">🔴 注入滚动体故障</el-button>
              <div style="font-size:12px;color:#909399;line-height:1.7">
                注入后流引擎立即按故障特征频率合成冲击信号，
                振动 RMS 升高触发 3σ/隔离森林预警，温度随之上升。
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

      <div class="panel">
        <div class="panel-title">
          <span>机器学习预测（XGBoost / 随机森林）</span>
          <div>
            <el-button type="primary" size="small" :loading="predicting" @click="runPrediction">▶ 运行预测</el-button>
            <el-button size="small" :loading="rulLoading" @click="runRulDemo">⏳ 退化场景演示（RUL）</el-button>
          </div>
        </div>
        <el-row :gutter="14">
          <el-col :span="12">
            <div v-if="prediction" style="font-size:13px">
              <div style="margin-bottom:8px">
                预测结论：<b :style="{color: prediction.pred_class===0?'#67c23a':'#f56c6c'}">{{ prediction.pred_label }}</b>
                <span style="color:#909399">（模型 {{ prediction.model }} {{ prediction.model_version }}）</span>
              </div>
              <div v-for="(p, name) in prediction.probs" :key="name" style="margin:6px 0">
                <div style="display:flex;justify-content:space-between;font-size:12px;color:#606266">
                  <span>{{ name }}</span><span>{{ (p*100).toFixed(1) }}%</span>
                </div>
                <el-progress :percentage="Math.round(p*100)" :color="name==='正常' ? '#67c23a' : '#f56c6c'" :show-text="false" style="margin-top:2px" />
              </div>
              <div style="margin-top:10px">
                健康评分：<b style="font-size:16px" :style="{color: prediction.health_score>=60?'#67c23a':'#f56c6c'}">{{ prediction.health_score }}</b>
                <span style="margin-left:14px;color:#909399">剩余寿命：{{ prediction.rul_hours ? prediction.rul_hours + ' 小时' : '未检测到退化' }}</span>
              </div>
              <div v-if="!prediction.available" style="color:#e6a23c;margin-top:8px">{{ prediction.message }}</div>
            </div>
            <div v-else style="color:#c0c4cc;font-size:13px;padding:20px 0">点击"运行预测"对当前设备状态进行机器学习诊断</div>
          </el-col>
          <el-col :span="12">
            <div v-if="rulDemo" style="font-size:13px">
              <div style="margin-bottom:6px">
                退化场景：外圈故障 48 小时仿真历史，当前健康指标 <b>{{ rulDemo.hi_now }}</b>，
                估计剩余寿命 <b style="color:#f56c6c">{{ rulDemo.rul_hours }} 小时</b>
                <span style="color:#909399">（斜率 {{ rulDemo.slope_per_hour.toFixed(3) }} HI/小时）</span>
              </div>
              <div ref="rulChart" style="height:180px"></div>
            </div>
            <div v-else style="color:#c0c4cc;font-size:13px;padding:20px 0">点击"退化场景演示"查看 48 小时退化曲线与 RUL 外推</div>
          </el-col>
        </el-row>
      </div>

      <div class="panel">
        <div class="panel-title"><span>本设备预警记录</span></div>
        <el-table :data="alarms" border stripe size="small">
          <el-table-column prop="created_at" label="时间" width="160" />
          <el-table-column prop="type" label="类型" width="110">
            <template #default="{row}"><el-tag size="small" :type="row.level>=3?'danger':'warning'">{{ row.type }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="message" label="内容" min-width="300" />
          <el-table-column prop="value" label="触发值" width="90" />
          <el-table-column prop="status" label="状态" width="90" />
          <el-table-column label="操作" width="80" fixed="right">
            <template #default="{row}">
              <el-button v-if="row.status==='active'" link type="primary" @click="ack(row)">确认</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>
  </div>`,
  computed: {
    charFreqs() { return this.waveform ? this.waveform.char_freqs : {}; },
  },
  watch: {
    async deviceId(id) {
      this.device = null; this.rmsBuffer = []; this.tempBuffer = [];
      if (!id) return;
      const res = await api.get('/api/devices/' + id);
      this.device = res.data;
      this.connectWs();
      this.refreshAlarms();
      this.loadWaveform();
    },
  },
  methods: {
    /* WebSocket 实时推送；断开自动切轮询兜底 */
    connectWs() {
      if (this.ws) { try { this.ws.close(); } catch (e) {} }
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const token = localStorage.getItem('phx_token');
      this.ws = new WebSocket(`${proto}://${location.host}/ws/device/${this.deviceId}?token=${encodeURIComponent(token)}`);
      this.ws.onopen = () => { this.wsConnected = true; };
      this.ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.sample) this.pushSample(msg.sample);
        if (msg.alarm) {
          ElMessage.warning(`⚠️ ${msg.alarm.message}`);
          this.refreshAlarms();
        }
      };
      this.ws.onclose = () => {
        this.wsConnected = false;
        // 轮询兜底：2s 一次实时快照
        if (!this.pollTimer) {
          this.pollTimer = setInterval(async () => {
            try {
              const res = await api.get('/api/monitoring/realtime');
              const s = res.data.find(x => x.device_id === this.deviceId);
              if (s) this.pushSample(s);
            } catch (e) {}
          }, 2000);
        }
      };
      this.ws.onerror = () => this.ws.close();
    },
    pushSample(s) {
      const t = new Date(s.ts * 1000).toLocaleTimeString('zh-CN', { hour12: false });
      this.rmsBuffer.push([t, s.rms]);
      this.tempBuffer.push([t, s.temp]);
      if (this.rmsBuffer.length > 120) this.rmsBuffer.shift();
      if (this.tempBuffer.length > 120) this.tempBuffer.shift();
      this.renderLiveCharts();
    },
    renderLiveCharts() {
      const mk = (ref) => this.charts[ref] || (this.charts[ref] = echarts.init(this.$refs[ref]));
      const base = {
        grid: { left: 45, right: 12, top: 14, bottom: 24 },
        xAxis: { type: 'category', axisLabel: { fontSize: 10 } },
        series: [{ type: 'line', smooth: true, showSymbol: false,
                   areaStyle: { opacity: 0.15 }, data: [] }],
      };
      const rms = mk('rmsChart');
      rms.setOption({ ...base, series: [{ ...base.series[0], data: this.rmsBuffer,
        lineStyle: { color: '#2c4a7c' }, itemStyle: { color: '#2c4a7c' }, areaStyle: { opacity: 0.12 } }] });
      const temp = mk('tempChart');
      temp.setOption({ ...base, series: [{ ...base.series[0], data: this.tempBuffer,
        lineStyle: { color: '#e6a23c' }, itemStyle: { color: '#e6a23c' } }] });
    },
    async loadWaveform() {
      try {
        const res = await api.get(`/api/devices/${this.deviceId}/waveform`);
        this.waveform = res.data;
        const wc = this.charts.wave || (this.charts.wave = echarts.init(this.$refs.waveChart));
        wc.setOption({
          tooltip: { trigger: 'axis' },
          grid: [{ left: 45, right: 12, top: 14, height: '32%' },
                 { left: 45, right: 12, top: '60%', height: '30%' }],
          xAxis: [{ type: 'category', data: this.waveform.time, axisLabel: { fontSize: 9 } },
                  { type: 'value', gridIndex: 1, axisLabel: { fontSize: 9 } }],
          yAxis: [{ type: 'value' }, { type: 'value', gridIndex: 1 }],
          series: [
            { type: 'line', data: this.waveform.values, showSymbol: false, lineStyle: { width: 1, color: '#2c4a7c' } },
            { type: 'line', xAxisIndex: 1, yAxisIndex: 1, showSymbol: false,
              data: this.waveform.freq.map((f, i) => [f, this.waveform.mag[i]]),
              lineStyle: { width: 1, color: '#e6a23c' } },
          ],
        });
      } catch (e) { /* 忽略 */ }
    },
    async refreshAlarms() {
      try {
        const res = await api.get('/api/alarms', { params: { limit: 20 } });
        this.alarms = res.data.filter(a => a.device_id === this.deviceId);
      } catch (e) {}
    },
    async inject(cls) {
      try {
        await api.post('/api/monitoring/inject-fault', { device_id: this.deviceId, fault_class: cls });
        ElMessage.success(cls === 0 ? '已恢复正常状态' : '故障已注入，观察曲线与预警');
        const res = await api.get('/api/devices/' + this.deviceId);
        this.device = res.data;
        this.refreshAlarms();
      } catch (e) { ElMessage.error('注入失败'); }
    },
    async ack(row) {
      try {
        await api.post(`/api/alarms/${row.id}/ack`);
        this.refreshAlarms();
      } catch (e) {}
    },
    async runPrediction() {
      this.predicting = true;
      try {
        const res = await api.post(`/api/prediction/${this.deviceId}/run`);
        this.prediction = res.data;
        if (!res.data.available) ElMessage.warning('模型未训练，请运行 train.bat');
      } catch (e) { ElMessage.error('预测失败'); }
      this.predicting = false;
    },
    async runRulDemo() {
      this.rulLoading = true;
      try {
        const res = await api.post('/api/prediction/rul-demo',
          { device_id: this.deviceId, fault_class: 2 });
        this.rulDemo = res.data;
        this.$nextTick(() => {
          const c = this.charts.rul || (this.charts.rul = echarts.init(this.$refs.rulChart));
          c.setOption({
            tooltip: { trigger: 'axis' },
            grid: { left: 45, right: 12, top: 12, bottom: 24 },
            xAxis: { type: 'category',
              data: this.rulDemo.history.map((h, i) => (i % 6 === 0 ? i + 'h' : '')),
              axisLabel: { fontSize: 10 } },
            yAxis: { type: 'value', min: 0, max: 1 },
            series: [
              { type: 'line', showSymbol: false, name: '健康指标 HI',
                data: this.rulDemo.history.map(h => h.hi),
                lineStyle: { color: '#2c4a7c' },
                markLine: { data: [{ yAxis: 0.15, label: { formatter: '失效阈值 0.15' },
                                     lineStyle: { color: '#f56c6c', type: 'dashed' } }] } },
            ],
          });
        });
      } catch (e) { ElMessage.error('退化演示失败'); }
      this.rulLoading = false;
    },
    onResize() { Object.values(this.charts).forEach(c => c.resize()); },
  },
  mounted() {
    this.waveTimer = setInterval(() => { if (this.deviceId) this.loadWaveform(); }, 3000);
    window.addEventListener('resize', this.onResize);
    if (this.deviceId) {
      // 从看板跳转过来时 device_id 已有值（watch 不触发），主动初始化
      this.$nextTick(async () => {
        const res = await api.get('/api/devices/' + this.deviceId);
        this.device = res.data;
        this.connectWs(); this.refreshAlarms(); this.loadWaveform();
      });
    }
  },
  beforeUnmount() {
    clearInterval(this.waveTimer);
    if (this.pollTimer) clearInterval(this.pollTimer);
    if (this.ws) { try { this.ws.close(); } catch (e) {} }
    window.removeEventListener('resize', this.onResize);
    Object.values(this.charts).forEach(c => c.dispose());
  },
};

/* ============ 以下页面在后续里程碑实现（占位） ============ */
window.Pages.Chat = { template: `<div class="panel">智能诊断对话建设中（里程碑 M8）</div>` };
window.Pages.Workorders = { template: `<div class="panel">工单管理建设中（里程碑 M9）</div>` };
window.Pages.Knowledge = { template: `<div class="panel">知识库管理建设中（里程碑 M7）</div>` };
