// 展示用的标签 / 颜色常量,集中一处。
// (Python 端这些在 app.py 和 config/labels.py 里重复了两份 —— 这里只留一份。)

// 5 个评分维度,固定顺序(与引擎 dim_scores / dim_avg 的 key 对应)。
export const DIMENSIONS = [
  { key: 'D1_flow_compliance', short: 'D1 流程', name: '流程遵循度', weight: 25 },
  { key: 'D2_task_completion', short: 'D2 任务', name: '任务完成度', weight: 25 },
  { key: 'D3_constraint_compliance', short: 'D3 约束', name: '约束遵循度', weight: 20 },
  { key: 'D4_knowledge_accuracy', short: 'D4 知识', name: '知识准确性', weight: 15 },
  { key: 'D5_dialogue_quality', short: 'D5 对话', name: '对话质量', weight: 15 },
]

// persona id → 中文标签(报告里展示用;配置页的可选项由后端 /api/config 提供)。
export const PERSONA_LABELS = {
  cooperative: '🤝 合作型',
  refuse_persistent: '😤 坚持拒绝型',
  out_of_scope: '🌀 越界提问型',
  interruption: '✋ 打断型',
  state_busy: '🚗 状态型(忙/开车)',
  ambiguous: '🤔 模糊型',
  adversarial: '⚔️ 对抗型',
  probing: '❓ 提问型',
}

// verifier 类型 → 中文标签(甜甜圈图切片名)。
export const VERIFIER_LABELS = {
  rule: '📏 规则',
  rule_pattern: '🔤 模式匹配',
  state_tracker: '🔄 流程追踪',
  llm_extract_then_rule: '🤖 LLM抽取',
  llm_judge: '⚖️ LLM判定',
}

// ColorBrewer Set2(沿用原 Plotly px.colors.qualitative.Set2),按切片顺序取色。
export const SET2 = ['#66c2a5', '#fc8d62', '#8da0cb', '#e78ac3', '#a6d854', '#ffd92f', '#e5c494', '#b3b3b3']

// 品牌紫(雷达描边 / 填充 / 分数卡渐变)。
export const BRAND = 'rgb(102,126,234)'
export const BRAND_FILL = 'rgba(102,126,234,0.3)'

// 分数 → 等级配色(深色, 浅色, 等级名)。85/70/50 阈值与引擎一致。
export function gradeColor(score) {
  if (score == null) return { dark: '#94a3b8', light: '#cbd5e1', grade: '无法评测' }
  if (score >= 85) return { dark: '#16a34a', light: '#22c55e', grade: '优秀' }
  if (score >= 70) return { dark: '#f59e0b', light: '#fbbf24', grade: '良好' }
  if (score >= 50) return { dark: '#ea580c', light: '#fb923c', grade: '需改进' }
  return { dark: '#dc2626', light: '#f87171', grade: '不合格' }
}

// persona 进度条用的单色(同样 85/70/50 阈值)。
export function barColor(score) {
  if (score == null) return '#94a3b8'
  if (score >= 85) return '#16a34a'
  if (score >= 70) return '#f59e0b'
  if (score >= 50) return '#ea580c'
  return '#dc2626'
}

// 分数展示: null(无法评测)显示破折号,否则保留原值。
export function fmtScore(score) {
  return score == null ? '—' : score
}
