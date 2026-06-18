import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { router } from './router'
import { EvalProvider } from './context/EvalContext'
import './index.css'

// EvalProvider 包在 RouterProvider 外层 —— 路由切换不会卸载它,
// 所以跨页共享的配置 / 运行状态 / 结果都不会丢。
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <EvalProvider>
      <RouterProvider router={router} />
    </EvalProvider>
  </React.StrictMode>,
)
