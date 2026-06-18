import { PERSONA_LABELS, barColor, fmtScore } from '../constants/labels'
import styles from './PersonaBars.module.css'

// 各 persona 的得分横条。breakdown 已由后端按分数升序排好(最弱在前)。
// onSelect 可选: 给了就让每行可点击(报告页点行 → 进单通详查)。
export default function PersonaBars({ breakdown, onSelect }) {
  const clickable = typeof onSelect === 'function'
  return (
    <div className={styles.list}>
      {breakdown.map((p) => {
        const pct = p.final_score == null ? 0 : Math.round(p.final_score)
        const color = barColor(p.final_score)
        return (
          // key 用后端稳定 id(dialogue_id),不用数组下标
          <div
            className={`${styles.row} ${clickable ? styles.clickable : ''}`}
            key={p.dialogue_id}
            onClick={clickable ? () => onSelect(p.dialogue_id) : undefined}
            // 可点击行做成键盘可达: 当作 button,支持 Tab 聚焦 + Enter/Space 触发
            onKeyDown={
              clickable
                ? (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSelect(p.dialogue_id)
                    }
                  }
                : undefined
            }
            role={clickable ? 'button' : undefined}
            tabIndex={clickable ? 0 : undefined}
            title={clickable ? '查看该通详情' : undefined}
          >
            <div className={styles.name}>{PERSONA_LABELS[p.persona_id] || p.persona_id}</div>
            <div className={styles.track}>
              <div className={styles.fill} style={{ width: `${pct}%`, background: color }} />
            </div>
            <div className={styles.score} style={{ color }}>
              {fmtScore(p.final_score)}
            </div>
          </div>
        )
      })}
    </div>
  )
}
