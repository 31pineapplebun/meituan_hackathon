import styles from './Loading.module.css'

export default function Loading({ text = '加载中…' }) {
  return (
    <div className={styles.wrap}>
      <div className={styles.spinner} />
      <div className={styles.text}>{text}</div>
    </div>
  )
}
