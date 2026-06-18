import { VERIFIER_LABELS } from '../constants/labels'
import styles from './VerdictTable.module.css'

// 判定枚举 → 展示文案 + 配色类
const VERDICT_META = {
  pass: { label: '✅ 通过', cls: 'pass' },
  fail: { label: '❌ 失败', cls: 'fail' },
  na: { label: '➖ 不适用', cls: 'na' },
  error: { label: '⚠️ 错误', cls: 'error' },
  not_implemented: { label: '🚧 未实现', cls: 'na' },
}

// 逐约束判定表。数据从 props 进;每行用 constraint_id 作 key(单通内唯一)。
export default function VerdictTable({ verdicts }) {
  if (!verdicts || verdicts.length === 0) {
    return <div className={styles.empty}>无约束判定明细。</div>
  }
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>约束 ID</th>
          <th>约束名</th>
          <th>判定</th>
          <th>校验方式</th>
          <th>理由 / 证据</th>
        </tr>
      </thead>
      <tbody>
        {verdicts.map((v) => {
          const m = VERDICT_META[v.verdict] || { label: v.verdict, cls: 'na' }
          return (
            <tr key={v.constraint_id}>
              <td className={styles.mono}>{v.constraint_id}</td>
              <td>{v.constraint_name}</td>
              <td>
                <span className={`${styles.badge} ${styles[m.cls]}`}>{m.label}</span>
              </td>
              <td className={styles.vtype}>{VERIFIER_LABELS[v.verifier_type] || v.verifier_type}</td>
              <td className={styles.reason}>{v.reason || v.evidence || '—'}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
