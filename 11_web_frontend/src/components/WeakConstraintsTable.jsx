import styles from './WeakConstraintsTable.module.css'

// 最常失败的约束表(后端已按失败率降序、最多 10 条)。
export default function WeakConstraintsTable({ items }) {
  if (!items || items.length === 0) {
    return <div className={styles.empty}>🎉 没有失败的约束,表现稳定。</div>
  }
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>约束 ID</th>
          <th>约束名</th>
          <th className={styles.num}>失败率</th>
          <th className={styles.num}>失败 / 总数</th>
        </tr>
      </thead>
      <tbody>
        {items.map((c) => (
          // key 用 constraint_id(后端稳定 id)
          <tr key={c.constraint_id}>
            <td className={styles.mono}>{c.constraint_id}</td>
            <td>{c.constraint_name || '—'}</td>
            <td className={styles.num}>
              <span className={styles.rate}>{c.fail_rate}%</span>
            </td>
            <td className={styles.num}>
              {c.fail_count} / {c.total_count}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
