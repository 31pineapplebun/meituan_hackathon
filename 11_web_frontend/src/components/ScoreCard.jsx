import { gradeColor, fmtScore } from '../constants/labels'
import styles from './ScoreCard.module.css'

// 大分数卡: 渐变背景随分数变色,大号分数 + 等级 + 一句话诊断。
export default function ScoreCard({ score, grade, diagnosis }) {
  const { dark, light, grade: fallbackGrade } = gradeColor(score)
  return (
    <div
      className={styles.card}
      style={{ background: `linear-gradient(135deg, ${dark} 0%, ${light} 100%)` }}
    >
      <div className={styles.scoreRow}>
        <span className={styles.score}>{fmtScore(score)}</span>
        <span className={styles.outOf}>/ 100</span>
        <span className={styles.grade}>{grade || fallbackGrade}</span>
      </div>
      {diagnosis && <div className={styles.diagnosis}>💡 {diagnosis}</div>}
    </div>
  )
}
