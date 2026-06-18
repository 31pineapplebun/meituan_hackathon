# CLAUDE.md — 外呼指令遵循自动评测系统（前端 React 重构）

## 项目简介
把外呼质检从"人工逐条审听"升级为"机器自动评测 + 人工监督"的内部工具。用户配置被测话术/指令与评测参数，系统用大模型模拟多类用户做多轮对话、自动判定合规，产出可定位到具体问题的评分报告与可视化。

## 重构背景（重要）
- 这是一次**前端重写**：原版前端是 Streamlit（多页 + Plotly + 自定义 CSS）。现在用 **React + Vite** 重做成一个多页 SPA。
- **评测引擎不动**：沿用已有的 Python 评测逻辑（大模型模拟用户、按成本分层判定——客观约束走规则、仅主观判断才调大模型、缓存 / 并发 / 固定随机种子保证可复现）。把它包成 **FastAPI 接口**，前端通过 REST 调用，不要重写引擎。
- 这是一个**学习 + 面试项目**。请优先写「我能读懂、能讲清楚」的代码：清晰、地道的 React，不过度抽象、不过早优化。非直观决定留一行注释说明**为什么**。
- **取代 Streamlit 是核心叙事**：代码与结构要能支撑我讲清"为什么 Streamlit 适合快速原型、不适合生产 / 定制 UI，所以迁到 React + FastAPI"。

## 技术栈
- React 18（函数组件 + Hooks）
- Vite
- React Router（多页：配置 / 运行 / 报告）
- React Context（跨页共享评测配置、运行状态、结果）
- react-plotly.js（沿用原 Plotly 图表，迁移成本最低）
- 原生 `fetch`（请求显式可见）
- CSS Modules
- JavaScript（JSX）。先把 React 吃透，暂不用 TS。

## 常用命令
```bash
npm install
npm run dev        # http://localhost:5173
npm run build
npm run preview
npm run lint
```

## 目录结构
```
src/
  api/
    evalApi.js          # FastAPI 接口封装
  context/
    EvalContext.jsx      # 跨页共享状态（配置 / 运行状态 / 结果）
  pages/
    ConfigPage.jsx       # 配置话术 / 指令与参数
    RunPage.jsx          # 触发评测 + 进度
    ReportPage.jsx       # 评分报告 + 图表 + 下载
  components/            # 复用组件（表单项、结果表格、图表封装、Loading 等）
  router.jsx            # 路由表
  App.jsx
  main.jsx
```

## 后端接口（按你的真实后端调整）
- `POST /api/evaluate`：提交配置、启动评测；直接返回结果，或返回 `job_id` 由前端轮询。
- `GET /api/jobs/{id}`：查询进度 / 状态（若用异步任务）。
- `GET /api/report/{id}`：取评分报告数据（含可定位到具体问题的明细）。
- `GET /api/report/{id}/html`：返回可下载的自包含 HTML 报告（沿用原功能）。

## 约定与规则
- **只用函数组件 + Hooks**。
- **跨页共享的状态（配置、运行状态、结果）放进 `EvalContext`**，不要用 props 一层层往下穿；页面内部的局部状态用 `useState`。
- 配置表单用**受控组件**（`value` + `onChange`）。
- 评测是耗时任务：`RunPage` 必须处理 **提交中 / 运行中（带进度）/ 完成 / 失败** 状态；若后端是异步任务，用轮询，并在组件卸载时清理定时器（`useEffect` 的清理函数）。
- 图表封装成独立组件，数据从 props 进；结果表格 / 列表渲染**用稳定 key**（用后端 id，不用下标）。
- 路由用 React Router；页面切换不能丢失 `EvalContext` 里的结果。
- **不要随意加依赖**（尤其别引重型 UI 库 / 状态管理库）；确需再解释理由。

## 这个项目应清晰体现的 React 概念（面试要能指着代码讲）
React Router 多页路由、**Context 跨组件状态共享**（以及"什么时候该上 Context、什么时候不必"）、受控表单、**耗时任务的异步状态机 + 轮询 + `useEffect` 清理**、列表 / 表格渲染与 key、组件拆分、图表组件封装。以及 **Streamlit → React 的取舍**要能完整讲出来。
