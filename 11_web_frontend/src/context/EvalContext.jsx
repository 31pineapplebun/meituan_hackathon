import { createContext, useContext, useState } from 'react'

// 跨页共享的状态都放这儿(见 CLAUDE.md):
//  - configMeta: 后端 /api/config 的返回(可选项),拉一次就缓存,避免重复请求
//  - form:       配置表单的选择(受控),要在「配置/运行/报告」之间来回切换时不丢
//  - jobId:      当前评测任务 id
//  - report:     评测报告结果
// 页面内部的临时状态(loading / 错误提示等)仍用各自的 useState,不往这里塞。
const EvalContext = createContext(null)

export function EvalProvider({ children }) {
  const [configMeta, setConfigMeta] = useState(null)
  const [form, setForm] = useState({
    instructionName: '',
    modelName: 'deepseek-v4-flash',
    personaList: [],
    mode: 'fast',
    customText: '', // 自定义指令原文(instructionName === custom_id 时使用)
  })
  const [jobId, setJobId] = useState(null)
  const [report, setReport] = useState(null)
  const [detailDialogueId, setDetailDialogueId] = useState(null) // 单通详查当前选中的对话

  const value = {
    configMeta,
    setConfigMeta,
    form,
    setForm,
    jobId,
    setJobId,
    report,
    setReport,
    detailDialogueId,
    setDetailDialogueId,
  }
  return <EvalContext.Provider value={value}>{children}</EvalContext.Provider>
}

// 自定义 hook: 收口 useContext + 守卫,组件里 useEval() 即可拿到共享状态。
export function useEval() {
  const ctx = useContext(EvalContext)
  if (!ctx) throw new Error('useEval 必须在 <EvalProvider> 内使用')
  return ctx
}
