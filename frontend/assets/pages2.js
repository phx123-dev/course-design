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

/* ============ 以下页面在后续里程碑实现（占位） ============ */
window.Pages.Dashboard = { template: `<div class="panel">健康看板建设中（里程碑 M5）</div>` };
window.Pages.Monitoring = { template: `<div class="panel">设备监控建设中（里程碑 M5）</div>` };
window.Pages.Chat = { template: `<div class="panel">智能诊断对话建设中（里程碑 M8）</div>` };
window.Pages.Workorders = { template: `<div class="panel">工单管理建设中（里程碑 M9）</div>` };
window.Pages.Knowledge = { template: `<div class="panel">知识库管理建设中（里程碑 M7）</div>` };
