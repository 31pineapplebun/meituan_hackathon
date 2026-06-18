import styles from './ProgressBar.module.css'

// 进度条。total>0 时按比例显示;否则(还没开始/快速演示)走不确定态动画。
export default function ProgressBar({ current, total, msg }) {
  const determinate = total > 0
  const pct = determinate ? Math.min(100, Math.round((current / total) * 100)) : null

  return (
    <div>
      <div className={styles.track}>
        <div
          className={determinate ? styles.fill : `${styles.fill} ${styles.indeterminate}`}
          style={determinate ? { width: `${pct}%` } : undefined}
        />
      </div>
      <div className={styles.label}>
        {msg}
        {determinate && <span className={styles.pct}>{pct}%</span>}
      </div>
    </div>
  )
}
