import { useNavigate } from 'react-router-dom'
import { useEval } from '../context/EvalContext'
import RadarChart from '../components/RadarChart'
import VerdictTable from '../components/VerdictTable'
import Transcript from '../components/Transcript'
import { PERSONA_LABELS, fmtScore, gradeColor } from '../constants/labels'
import styles from './DetailPage.module.css'

// 单通详查: 从报告的 per_dialogue_results 里下钻某一通对话。数据已在 Context 里,无需再请求后端。
export default function DetailPage() {
  const { report, detailDialogueId, setDetailDialogueId } = useEval()
  const navigate = useNavigate()

  if (!report || report.error) {
    return (
      <div className={styles.empty}>
        <p>还没有可详查的对话,请先完成一次评测。</p>
        <button className={styles.btn} onClick={() => navigate('/config')}>
          去配置评测 →
        </button>
      </div>
    )
  }

  const dialogues = report.per_dialogue_results || []
  if (dialogues.length === 0) return <div className={styles.empty}>这份报告没有可下钻的对话。</div>

  // 选中对话: Context 里指定的,否则默认第一通
  const current = dialogues.find((d) => d.dialogue_id === detailDialogueId) || dialogues[0]
  const sr = current.score_report || {}
  const turns = current.dialogue?.turns || []
  const cpr = sr.critical_pass_rate == null ? null : Math.round(sr.critical_pass_rate * 100)
  const gc = gradeColor(sr.final_score)

  return (
    <div className={styles.page}>
      <div className={styles.head}>
        <h2 className={styles.title}>单通详查</h2>
        <select
          className={styles.picker}
          value={current.dialogue_id}
          onChange={(e) => setDetailDialogueId(e.target.value)}
        >
          {dialogues.map((d) => (
            <option key={d.dialogue_id} value={d.dialogue_id}>
              {PERSONA_LABELS[d.persona_id] || d.persona_id} · {fmtScore(d.score_report?.final_score)} 分 ·{' '}
              {d.dialogue_id}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.metrics}>
        <div className={styles.metric}>
          <div className={styles.mLabel}>本通得分</div>
          <div className={styles.mValue} style={{ color: gc.dark }}>{fmtScore(sr.final_score)}</div>
        </div>
        <div className={styles.metric}>
          <div className={styles.mLabel}>场景</div>
          <div className={styles.mValueSm}>{PERSONA_LABELS[current.persona_id] || current.persona_id}</div>
        </div>
        <div className={styles.metric}>
          <div className={styles.mLabel}>Critical 通过率</div>
          <div className={styles.mValueSm}>{cpr == null ? '—' : `${cpr}%`}</div>
        </div>
        <div className={styles.metric}>
          <div className={styles.mLabel}>轮数</div>
          <div className={styles.mValueSm}>{current.n_turns ?? turns.length}</div>
        </div>
      </div>

      {sr.red_line_violations?.length > 0 && (
        <div className={styles.redline}>
          🚨 红线违规:{sr.red_line_violations.join('、')}
          {sr.ceiling_reason ? `(${sr.ceiling_reason})` : ''}
        </div>
      )}

      <div className={styles.grid2}>
        <section className={styles.card}>
          <h3 className={styles.cardTitle}>五维得分</h3>
          <RadarChart dimAvg={sr.dim_scores} />
        </section>
        <section className={styles.card}>
          <h3 className={styles.cardTitle}>💬 对话内容</h3>
          <Transcript turns={turns} />
        </section>
      </div>

      <section className={styles.card}>
        <h3 className={styles.cardTitle}>📋 逐约束判定</h3>
        <VerdictTable verdicts={current.verdict_details} />
      </section>

      {current.detailed_suggestions?.length > 0 && (
        <section className={styles.card}>
          <h3 className={styles.cardTitle}>💡 本通优化建议</h3>
          <div className={styles.suggestions}>
            {current.detailed_suggestions.map((s, i) => (
              <details className={styles.sugg} key={`${s.constraint_id}-${i}`}>
                <summary>
                  <span className={styles.prio}>{s.priority}</span>
                  <span className={styles.suggHead}>
                    {s.constraint_id} · {s.problem}
                  </span>
                </summary>
                {s.how_to_fix && (
                  <p className={styles.suggBody}>
                    <b>改进:</b> {s.how_to_fix}
                  </p>
                )}
                {s.example && <pre className={styles.example}>{s.example}</pre>}
              </details>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
