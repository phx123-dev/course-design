/* 公共组件库（全局注册） */
'use strict';
window.Components = window.Components || {};

/* 健康状态标签：绿色正常 / 黄色外圈 / 红色内圈·滚动体 */
window.Components.HealthTag = {
  props: { state: { type: Number, default: 0 }, size: { type: String, default: 'small' } },
  template: `
    <el-tag :size="size" :type="typeMap[state]" effect="light">{{ labelMap[state] }}</el-tag>`,
  computed: {
    labelMap() { return { 0: '正常', 1: '内圈故障', 2: '外圈故障', 3: '滚动体故障' }; },
    typeMap() { return { 0: 'success', 1: 'danger', 2: 'warning', 3: 'danger' }; },
  },
};

/* 工单状态标签 */
window.Components.WoStatusTag = {
  props: { status: String },
  template: `
    <el-tag size="small" :type="{待处理:'danger',进行中:'warning',已完成:'success'}[status]" effect="light">
      {{ status }}
    </el-tag>`,
};

/* 设备选择下拉（跨页共用：从 API 拉取台账列表） */
window.Components.DeviceSelect = {
  props: { modelValue: [Number, null], placeholder: { type: String, default: '选择设备' }, clearable: { type: Boolean, default: true } },
  emits: ['update:modelValue'],
  data() { return { list: [], loading: false }; },
  template: `
    <el-select :model-value="modelValue" :placeholder="placeholder" :clearable="clearable" filterable
               :loading="loading" @update:model-value="$emit('update:modelValue', $event)">
      <el-option v-for="d in list" :key="d.id" :label="d.code + ' ' + d.name" :value="d.id">
        <span style="margin-right:6px">{{ d.code }}</span>
        <span style="color:#909399;font-size:12px">{{ d.name }}</span>
        <health-tag :state="d.health_state" style="float:right" />
      </el-option>
    </el-select>`,
  mounted() { this.load(); },
  methods: {
    async load() {
      this.loading = true;
      try {
        const res = await api.get('/api/devices');
        this.list = res.data;
      } catch (e) { /* 忽略 */ }
      this.loading = false;
    },
  },
  components: {},
};

/* 依据溯源卡片：展示诊断结论引用的知识来源与数据证据 */
window.Components.EvidenceCard = {
  props: { evidence: { type: Array, default: () => [] } },
  template: `
    <div v-if="evidence && evidence.length" class="evidence-card">
      <div style="font-weight:700;margin-bottom:4px">📎 依据溯源（知识来源 + 数据证据）</div>
      <div v-for="(ev, i) in evidence" :key="i" style="margin:3px 0">
        [{{ ev.ref }}] {{ ev.title }}
        <span class="src">（{{ ev.source }} · 相似度 {{ ev.score.toFixed(2) }}）</span>
      </div>
    </div>`,
};
