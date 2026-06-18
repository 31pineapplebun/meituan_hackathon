import ScoreCard from './ScoreCard'
import RadarChart from './RadarChart'
import VerdictTable from './VerdictTable'
import Transcript from './Transcript'
import styles from './SingleReport.module.css'

function downloadJson(output) {
  const blob = new Blob([JSON.stringify(output, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'single_dialogue_eval.json'
  a.click()
  URL.revokeObjectURL(url)
}

// 单通质检结果。run_pipeline 的输出 shape 和详查页一样,所以复用 ScoreCard/RadarChart/
// VerdictTable/Transcript 这几个组件。
export default function SingleReport({ output }) {
  const sr = output.score_report || {}
  const stats = output.stats || {}
  const turns = output.dialogue?.turns || []

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <div className={styles.meta}>
          评分标尺:{output.rubric_label}
          {output.mock_mode && ' · ⚠️ mock 预览(未设 key,主观约束多为未判定)'}
        </div>
        <button className={styles.btn} onClick={() => downloadJson(output)}>
          ⬇ 下载 JSON
        </button>
      </div>

      <ScoreCard score={sr.final_score} diagnosis={null} />
      {sr.final_score == null && (
        <div className={styles.note}>
          无法对这通对话评分(对话为空,或全部约束 na / 未判定)。mock 模式下主观约束需设
          DEEPSEEK_API_KEY 才能真判。
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
        <div className={styles.stats}>
          <span>共 {stats.total_constraints ?? 0}</span>
          <span className={styles.pass}>pass {stats.pass ?? 0}</span>
          <span className={styles.fail}>fail {stats.fail ?? 0}</span>
          <span className={styles.na}>na {stats.na ?? 0}</span>
          {stats.not_implemented ? <span className={styles.na}>未判定 {stats.not_implemented}</span> : null}
        </div>
        <VerdictTable verdicts={output.verdict_details} />
      </section>
    </div>
  )
}
