import styles from './Transcript.module.css'

// 对话回放(聊天气泡)。assistant=客服(左)、user=用户(右)。数据从 props 进。
export default function Transcript({ turns }) {
  if (!turns || turns.length === 0) {
    return <div className={styles.empty}>此对话未保存逐轮内容(完整模式真跑会有完整对话)。</div>
  }
  return (
    <div className={styles.list}>
      {turns.map((t, i) => {
        const isAssistant = t.role === 'assistant'
        return (
          <div key={t.turn ?? i} className={`${styles.row} ${isAssistant ? styles.left : styles.right}`}>
            <div className={styles.who}>
              {isAssistant ? '🧑‍💼 客服' : '🙋 用户'} <span className={styles.turn}>T{t.turn ?? i + 1}</span>
            </div>
            <div className={`${styles.bubble} ${isAssistant ? styles.bubbleA : styles.bubbleU}`}>
              {t.content}
            </div>
          </div>
        )
      })}
    </div>
  )
}
