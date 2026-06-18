// FastAPI 接口封装。用原生 fetch(请求显式可见)。
// 开发期 BASE='/api' 走 Vite 代理转给 localhost:8000(见 vite.config.js)。
const BASE = '/api'

// 统一处理: 非 2xx 抛错,并尽量取出后端的 detail 文案(FastAPI 的 HTTPException 放在 detail)。
async function http(path, options) {
  const res = await fetch(BASE + path, options)
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body && body.detail) detail = body.detail
    } catch {
      /* 响应不是 JSON 就用默认文案 */
    }
    throw new Error(detail)
  }
  return res.json()
}

export function getConfig() {
  return http('/config')
}

export function startEvaluation(payload) {
  return http('/evaluate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function getJob(jobId) {
  return http(`/jobs/${jobId}`)
}

export function getReport(jobId) {
  return http(`/report/${jobId}`)
}

export function getInstructionMd(id) {
  return http(`/instruction/${id}/md`)
}

export function evalDialogue(dialogueText) {
  return http('/eval-dialogue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dialogue_text: dialogueText }),
  })
}

export function simulateEval(promptText) {
  return http('/simulate-eval', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_text: promptText }),
  })
}
