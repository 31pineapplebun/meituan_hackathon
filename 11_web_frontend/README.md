# 11_web_frontend — React + Vite 前端

外呼指令遵循评测系统的前端,**取代原 Streamlit UI**。多页 SPA:配置 → 运行 → 报告。

## 跑起来

```bash
# 1. 先启动后端(另一个终端)
cd ../12_api
python -m uvicorn main:app --app-dir . --port 8000

# 2. 启动前端
npm install
npm run dev        # http://localhost:5173
```

Vite dev server 会把 `/api` 代理到 `http://localhost:8000`(见 `vite.config.js`),所以前端是同源请求,无需配置跨域。

```bash
npm run build      # 产出 dist/
npm run preview    # 本地预览生产构建
```

## 结构

```
src/
  api/evalApi.js          FastAPI 接口封装(原生 fetch)
  context/EvalContext.jsx  跨页共享状态(配置 / 运行状态 / 结果)
  constants/labels.js      维度 / persona / verifier 标签 + 配色(集中一处)
  pages/
    ConfigPage.jsx         受控表单:指令 / 模型 / persona / 模式
    RunPage.jsx            异步状态机:轮询任务进度 + useEffect 清理
    ReportPage.jsx         评分报告 + Plotly 图表 + 下载
  components/             RadarChart / DonutChart / ScoreCard / PersonaBars /
                         WeakConstraintsTable / ProgressBar / Loading
  router.jsx             路由表(/config /run /report)
  App.jsx               外层布局(头部 + 步骤导航)
  main.jsx              入口(EvalProvider 包在 RouterProvider 外,切页不丢状态)
```

## 体现的 React 概念

- React Router 多页路由 + 共享布局(`<Outlet/>`)
- **Context 跨页共享状态**(配置 / 运行 / 结果),页内临时状态仍用 `useState`
- 受控表单(`value` + `onChange`)
- **耗时任务的异步状态机 + 轮询 + `useEffect` 清理**(`RunPage`)
- 列表 / 表格用后端稳定 id 作 key
- 组件拆分 + 图表组件封装(数据从 props 进)

## 关于图表

用 `react-plotly.js` 的 factory + `plotly.js-dist-min` 接入(而非默认完整 `plotly.js`),
打包更友好。沿用原 Streamlit 的两张图:五维雷达(Scatterpolar)+ 校验方式甜甜圈(pie hole)。
