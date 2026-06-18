import { useNavigate } from 'react-router-dom'
import { useEval } from '../context/EvalContext'
import ScoreCard from '../components/ScoreCard'
import RadarChart from '../components/RadarChart'
import DonutChart from '../components/DonutChart'
import PersonaBars from '../components/PersonaBars'
import WeakConstraintsTable from '../components/WeakConstraintsTable'
import { VERIFIER_LABELS } from '../constants/labels'
import styles from './ReportPage.module.css'

// 甜甜圈数据: 统计这套约束用了哪些 verifier 类型。同一指令各对话共享同一套约束,
// 取 verdict_details 最全的一通即可代表整套约束集合。
function verifierDistribution(report) {
  const pdr = report.per_dialogue_results || []
  const longest = pdr.reduce(
    (best, r) =>
      (r.verdict_details?.length || 0) > (best?.verdict_details?.length || 0) ? r : best,
    null,
  )
  const details = longest?.verdict_details || []
  const counts = {}
  for (const v of details) {
    const label = VERIFIER_LABELS[v.verifier_type] || v.verifier_type
    counts[label] = (counts[label] || 0) + 1
  }
  return { labels: Object.keys(counts), values: Object.values(counts) }
}

function downloadJson(report) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `model_report_${report.instruction_name}_${report.model_name}.json`
  a.click()
  URL.revokeObjectURL(url)
}

export default function ReportPage() {
  const { report, setDetailDialogueId } = useEval()
  const navigate = useNavigate()

  if (!report) {
    return (
      <div className={styles.empty}>
        <p>还没有评测结果。</p>
        <button className={styles.btn} onClick={() => navigate('/config')}>
          去配置评测 →
        </button>
      </div>
    )
  }
  // 引擎在全部场景都无法评测时会返回 {error}
  if (report.error) {
    return (
      <div className={styles.errorBox}>
        <h3>无法生成报告</h3>
        <p>{report.error}</p>
        <button className={styles.btn} onClick={() => navigate('/config')}>
          返回配置
        </button>
      </div>
    )
  }

  const s = report.summary
  const donut = verifierDistribution(report)

  return (
    <div className={styles.page}>
      <div className={styles.head}>
        <div>
          <h2 className={styles.title}>评测报告</h2>
          <div className={styles.meta}>
            指令 <b>{report.instruction_name}</b> · 模型 <b>{report.model_name}</b> ·{' '}
            {report.generated_at} · {s.n_dialogues} 个场景平均 · 范围 {s.min_score}–{s.max_score}
            {s.n_unevaluable > 0 && ` · ${s.n_unevaluable} 个场景未纳入`}
          </div>
        </div>
        <button className={styles.btn} onClick={() => downloadJson(report)}>
          ⬇ 下载 JSON
        </button>
      </div>

      <ScoreCard score={s.avg_score} grade={s.grade} diagnosis={s.diagnosis} />

      <div className={styles.grid2}>
        <section className={styles.card}>
          <h3 className={styles.cardTitle}>五维能力雷达</h3>
          <RadarChart dimAvg={report.dim_avg} />
        </section>
        <section className={styles.card}>
          <h3 className={styles.cardTitle}>各场景表现(最弱在前)</h3>
          <PersonaBars
            breakdown={report.persona_breakdown}
            onSelect={(id) => {
              setDetailDialogueId(id)
              navigate('/detail')
            }}
          />
          <div className={styles.hint}>点击某行查看该通详情 →</div>
        </section>
      </div>

      <div className={styles.grid2}>
        <section className={styles.card}>
          <h3 className={styles.cardTitle}>最常失败的约束</h3>
          <WeakConstraintsTable items={report.weak_constraints} />
        </section>
        <section className={styles.card}>
          <h3 className={styles.cardTitle}>约束校验方式分布</h3>
          {donut.labels.length ? (
            <DonutChart labels={donut.labels} values={donut.values} />
          ) : (
            <div className={styles.muted}>无可统计的约束</div>
          )}
        </section>
      </div>
    </div>
  )
}
