import { useEffect, useRef, useState } from 'react'
import { evalDialogue, simulateEval, getJob, getReport } from '../api/evalApi'
import SingleReport from '../components/SingleReport'
import ProgressBar from '../components/ProgressBar'
import styles from './SinglePage.module.css'

// 单通质检: 自成一页(不走配置→运行→报告那条主流程)。两种来源:
//  - paste:    用户直接给一通对话
//  - describe: 用户给大致描述,系统模拟一通再评
// 结果是「单通报告」(shape 与详查页一致),内联渲染 SingleReport。
export default function SinglePage() {
  const [mode, setMode] = useState('paste') // paste | describe
  const [dialogueText, setDialogueText] = useState('')
  const [promptText, setPromptText] = useState('')
  const [phase, setPhase] = useState('idle') // idle | running | done | failed
  const [progressMsg, setProgressMsg] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const timerRef = useRef(null)
  const cancelledRef = useRef(false)

  // 卸载时停止轮询(异步任务的清理)
  useEffect(
    () => () => {
      cancelledRef.current = true
      if (timerRef.current) clearTimeout(timerRef.current)
    },
    [],
  )

  function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => setDialogueText(String(reader.result))
    reader.readAsText(file)
  }

  function pollJob(jobId) {
    getJob(jobId)
      .then((j) => {
        if (cancelledRef.current) return
        setProgressMsg(j.progress?.msg || '')
        if (j.status === 'done') {
          return getReport(jobId).then((rep) => {
            if (cancelledRef.current) return
            setResult(rep)
            if (rep.error) {
              setPhase('failed')
              setError(rep.error)
            } else {
              setPhase('done')
            }
          })
        }
        if (j.status === 'failed') {
          setPhase('failed')
          setError(j.error || '评测失败')
          return
        }
        timerRef.current = setTimeout(() => pollJob(jobId), 700)
      })
      .catch((e) => {
        if (!cancelledRef.current) {
          setPhase('failed')
          setError(e.message)
        }
      })
  }

  async function submit() {
    setError(null)
    setResult(null)
    setProgressMsg('提交中…')
    setPhase('running')
    cancelledRef.current = false
    try {
      const { job_id } =
        mode === 'paste' ? await evalDialogue(dialogueText) : await simulateEval(promptText)
      pollJob(job_id)
    } catch (e) {
      setPhase('failed')
      setError(e.message)
    }
  }

  const canSubmit =
    (mode === 'paste' ? dialogueText.trim() : promptText.trim()) && phase !== 'running'

  return (
    <div className={styles.page}>
      <h2 className={styles.title}>单通质检</h2>
      <p className={styles.intro}>
        评测某一通<strong>具体对话</strong>(不是评模型),用内置通用外呼质检标准打分。
      </p>

      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${mode === 'paste' ? styles.tabOn : ''}`}
          onClick={() => setMode('paste')}
        >
          💬 粘贴 / 上传一通对话
        </button>
        <button
          className={`${styles.tab} ${mode === 'describe' ? styles.tabOn : ''}`}
          onClick={() => setMode('describe')}
        >
          ✏️ 给个大致描述 → 模拟
        </button>
      </div>

      {mode === 'paste' ? (
        <section className={styles.card}>
          <div className={styles.bar}>
            <label className={styles.fileBtn}>
              📤 上传 .jsonl/.json/.txt
              <input type="file" accept=".jsonl,.json,.txt" hidden onChange={handleFile} />
            </label>
          </div>
          <textarea
            className={styles.textarea}
            rows={10}
            placeholder={'建议每行「客服: …」/「用户: …」(不标也能评,会按行交替猜角色)。\n也支持粘贴原生 .jsonl 内容。'}
            value={dialogueText}
            onChange={(e) => setDialogueText(e.target.value)}
          />
          <p className={styles.note}>不设 DEEPSEEK_API_KEY 时走 mock 预览:主观约束会显示「未判定」。</p>
        </section>
      ) : (
        <section className={styles.card}>
          <textarea
            className={styles.textarea}
            rows={5}
            placeholder="例: 生成一段易怒型用户和数字人客服关于外卖超时的对话"
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
          />
          <p className={styles.note}>系统据此先模拟一通对话再质检。需 DEEPSEEK_API_KEY。</p>
        </section>
      )}

      <button className={styles.submit} disabled={!canSubmit} onClick={submit}>
        {phase === 'running' ? '评测中…' : mode === 'paste' ? '🔍 评测这通对话' : '🎬 模拟并评测'}
      </button>

      {phase === 'running' && (
        <div className={styles.runBox}>
          <div className={styles.spinner} />
          <div className={styles.progressWrap}>
            <ProgressBar current={0} total={0} msg={progressMsg || '正在评测…'} />
          </div>
        </div>
      )}
      {phase === 'failed' && <div className={styles.error}>{error}</div>}
      {phase === 'done' && result && !result.error && <SingleReport output={result} />}
    </div>
  )
}
