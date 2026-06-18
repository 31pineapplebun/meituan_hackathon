import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useEval } from '../context/EvalContext'
import { getJob, getReport } from '../api/evalApi'
import ProgressBar from '../components/ProgressBar'
import styles from './RunPage.module.css'

// 评测是耗时任务。这一页就是一个异步状态机:
//   polling(轮询任务进度) → fetching(拉报告) → 跳报告页 / failed(失败)
export default function RunPage() {
  const { jobId, setReport, setJobId } = useEval()
  const navigate = useNavigate()
  const [job, setJob] = useState(null)
  const [phase, setPhase] = useState('polling') // polling | fetching | failed
  const [error, setError] = useState(null)
  const timerRef = useRef(null)

  useEffect(() => {
    // 没有 job(比如直接刷新到本页)→ 回配置页
    if (!jobId) {
      navigate('/config', { replace: true })
      return
    }
    let cancelled = false

    async function poll() {
      try {
        const j = await getJob(jobId)
        if (cancelled) return
        setJob(j)
        if (j.status === 'done') {
          setPhase('fetching')
          const rep = await getReport(jobId)
          if (cancelled) return
          setReport(rep)
          navigate('/report', { replace: true })
          return // 完成,停止轮询
        }
        if (j.status === 'failed') {
          setPhase('failed')
          setError(j.error || '评测失败')
          return
        }
        timerRef.current = setTimeout(poll, 700) // 仍在跑 → 700ms 后再查
      } catch (e) {
        if (cancelled) return
        setPhase('failed')
        setError(e.message)
      }
    }
    poll()

    // 清理: 组件卸载(或 jobId 变化)时取消回调 + 清定时器,
    // 防止卸载后还 setState / 轮询泄漏。
    return () => {
      cancelled = true
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [jobId, navigate, setReport])

  if (phase === 'failed') {
    return (
      <div className={styles.page}>
        <div className={styles.failBox}>
          <div className={styles.failIcon}>⚠️</div>
          <h3>评测失败</h3>
          <p className={styles.failMsg}>{error}</p>
          <button className={styles.btn} onClick={() => navigate('/config')}>
            返回配置
          </button>
        </div>
      </div>
    )
  }

  // 取消: 清掉 jobId 并回配置页。卸载本页会触发 useEffect 清理(停止前端轮询)。
  function cancel() {
    setJobId(null)
    navigate('/config')
  }

  const progress = job?.progress || { current: 0, total: 0, msg: '提交中…' }
  return (
    <div className={styles.page}>
      <div className={styles.runBox}>
        <div className={styles.spinner} />
        <h3>{phase === 'fetching' ? '正在拉取报告…' : '正在评测…'}</h3>
        <div className={styles.progressWrap}>
          <ProgressBar current={progress.current} total={progress.total} msg={progress.msg} />
        </div>
        <button className={styles.cancelBtn} onClick={cancel}>
          取消并返回配置
        </button>
        <p className={styles.cancelNote}>(完整运行会在后端继续跑完;前端仅停止轮询)</p>
      </div>
    </div>
  )
}
