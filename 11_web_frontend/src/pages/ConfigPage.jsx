import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useEval } from '../context/EvalContext'
import { getConfig, startEvaluation, getInstructionMd } from '../api/evalApi'
import Loading from '../components/Loading'
import styles from './ConfigPage.module.css'

export default function ConfigPage() {
  const { configMeta, setConfigMeta, form, setForm, setJobId, setReport } = useEval()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(!configMeta)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  // 首次进入拉取配置空间;已缓存则跳过(从报告页切回来不会重复请求)。
  useEffect(() => {
    if (configMeta) return
    let cancelled = false
    getConfig()
      .then((meta) => {
        if (cancelled) return
        setConfigMeta(meta)
        // 用后端给的默认值初始化表单(仅在表单还空着时)
        setForm((f) => ({
          ...f,
          instructionName: f.instructionName || meta.instructions[0]?.id || '',
          personaList: f.personaList.length
            ? f.personaList
            : meta.personas.filter((p) => p.default).map((p) => p.id),
        }))
        setLoading(false)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e.message)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [configMeta, setConfigMeta, setForm])

  const CUSTOM = configMeta?.custom_id || '__custom__'
  const isCustom = form.instructionName === CUSTOM
  const currentInstr = configMeta?.instructions.find((i) => i.id === form.instructionName)
  const fastAvailable = !isCustom && !!currentInstr?.has_demo

  // 选了没有预置数据的指令时,自动切到完整运行(快速演示不可用)。
  useEffect(() => {
    if (configMeta && !fastAvailable && form.mode === 'fast') {
      setForm((f) => ({ ...f, mode: 'full' }))
    }
  }, [configMeta, fastAvailable, form.mode, setForm])

  if (loading) return <Loading text="加载配置中…" />
  if (error && !configMeta)
    return (
      <div className={styles.error}>
        加载配置失败:{error}
        <br />
        请确认后端已启动:<code>python -m uvicorn main:app --app-dir 12_api --port 8000</code>
      </div>
    )

  const meta = configMeta

  function togglePersona(id) {
    setForm((f) => ({
      ...f,
      personaList: f.personaList.includes(id)
        ? f.personaList.filter((x) => x !== id)
        : [...f.personaList, id],
    }))
  }

  function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => setForm((f) => ({ ...f, customText: String(reader.result) }))
    reader.readAsText(file)
  }

  async function loadExample() {
    try {
      const { text } = await getInstructionMd('official_1_feimaotui')
      setForm((f) => ({ ...f, customText: text }))
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const { job_id } = await startEvaluation({
        instruction_name: form.instructionName,
        model_name: form.modelName,
        persona_list: form.personaList,
        mode: form.mode,
        custom_instruction_text: isCustom ? form.customText : '',
      })
      setReport(null) // 清掉上一次的结果
      setJobId(job_id)
      navigate('/run')
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  const canSubmit =
    (isCustom ? form.customText.trim() : form.instructionName) &&
    form.personaList.length > 0 &&
    !submitting

  return (
    <form className={styles.page} onSubmit={handleSubmit}>
      <h2 className={styles.title}>配置评测</h2>
      <p className={styles.intro}>
        给一条被测指令和一个待测模型,系统会模拟多类用户与它对话,并自动判定合规、给出评分报告。
      </p>

      <section className={styles.card}>
        <label className={styles.label}>任务指令</label>
        <div className={styles.sourceToggle}>
          <button
            type="button"
            className={`${styles.toggleBtn} ${!isCustom ? styles.toggleOn : ''}`}
            onClick={() => setForm((f) => ({ ...f, instructionName: meta.instructions[0]?.id || '' }))}
          >
            📚 预置指令
          </button>
          <button
            type="button"
            className={`${styles.toggleBtn} ${isCustom ? styles.toggleOn : ''}`}
            onClick={() => setForm((f) => ({ ...f, instructionName: CUSTOM, mode: 'full' }))}
          >
            ✍️ 自定义指令
          </button>
        </div>

        {!isCustom ? (
          <select
            className={styles.select}
            value={form.instructionName}
            onChange={(e) => setForm((f) => ({ ...f, instructionName: e.target.value }))}
          >
            {meta.instructions.map((i) => (
              <option key={i.id} value={i.id}>
                {i.label}
              </option>
            ))}
          </select>
        ) : (
          <div className={styles.custom}>
            <div className={styles.customBar}>
              <label className={styles.fileBtn}>
                📤 上传 .md/.txt
                <input type="file" accept=".md,.txt" hidden onChange={handleFile} />
              </label>
              <button type="button" className={styles.exampleBtn} onClick={loadExample}>
                填入示例(官方 Sample 1)
              </button>
            </div>
            <textarea
              className={styles.textarea}
              rows={12}
              placeholder="粘贴任务指令(Markdown)。建议用结构化格式 —— 可先点「填入示例」看格式再改。"
              value={form.customText}
              onChange={(e) => setForm((f) => ({ ...f, customText: e.target.value }))}
            />
            <p className={styles.note}>
              自定义指令走<strong>完整运行</strong>(需 API key);解析为离线启发式,结构化指令效果最好。
            </p>
          </div>
        )}
      </section>

      <section className={styles.card}>
        <label className={styles.label}>待测模型(让哪个模型来演「客服」)</label>
        <select
          className={styles.select}
          value={form.modelName}
          onChange={(e) => setForm((f) => ({ ...f, modelName: e.target.value }))}
        >
          {meta.models.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </section>

      <section className={styles.card}>
        <label className={styles.label}>
          模拟用户类型 <span className={styles.hint}>(已选 {form.personaList.length} 类)</span>
        </label>
        <div className={styles.personaGrid}>
          {meta.personas.map((p) => {
            const checked = form.personaList.includes(p.id)
            const noPreset = form.mode === 'fast' && !p.fast
            return (
              <label key={p.id} className={`${styles.persona} ${checked ? styles.personaOn : ''}`}>
                <input type="checkbox" checked={checked} onChange={() => togglePersona(p.id)} />
                <span>{p.label}</span>
                {noPreset && <span className={styles.noPreset}>无预置</span>}
              </label>
            )
          })}
        </div>
        {form.mode === 'fast' && (
          <p className={styles.note}>
            快速演示只覆盖未标「无预置」的 4 类;选了「无预置」的在快速模式会被跳过。
          </p>
        )}
      </section>

      <section className={styles.card}>
        <label className={styles.label}>评测模式</label>
        <div className={styles.modes}>
          <label
            className={`${styles.mode} ${form.mode === 'fast' ? styles.modeOn : ''} ${
              !fastAvailable ? styles.modeDisabled : ''
            }`}
          >
            <input
              type="radio"
              name="mode"
              value="fast"
              checked={form.mode === 'fast'}
              disabled={!fastAvailable}
              onChange={() => setForm((f) => ({ ...f, mode: 'fast' }))}
            />
            <div>
              <div className={styles.modeTitle}>⚡ 快速演示</div>
              <div className={styles.modeDesc}>读预置真实结果,秒出,无需 API key</div>
            </div>
          </label>
          <label className={`${styles.mode} ${form.mode === 'full' ? styles.modeOn : ''}`}>
            <input
              type="radio"
              name="mode"
              value="full"
              checked={form.mode === 'full'}
              onChange={() => setForm((f) => ({ ...f, mode: 'full' }))}
            />
            <div>
              <div className={styles.modeTitle}>🔬 完整运行</div>
              <div className={styles.modeDesc}>实时模拟对话 + 评测,需 API key,几分钟</div>
            </div>
          </label>
        </div>
      </section>

      {error && <div className={styles.error}>{error}</div>}

      <button type="submit" className={styles.submit} disabled={!canSubmit}>
        {submitting ? '提交中…' : '开始评测 →'}
      </button>
    </form>
  )
}
