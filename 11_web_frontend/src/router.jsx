import { createBrowserRouter, Navigate } from 'react-router-dom'
import App from './App'
import ConfigPage from './pages/ConfigPage'
import RunPage from './pages/RunPage'
import ReportPage from './pages/ReportPage'
import DetailPage from './pages/DetailPage'
import AboutPage from './pages/AboutPage'
import SinglePage from './pages/SinglePage'

// 三页流程: 配置 → 运行 → 报告。App 作为外层布局(头部 + 导航),子路由渲染到 <Outlet/>。
export const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/config" replace /> },
      { path: 'config', element: <ConfigPage /> },
      { path: 'run', element: <RunPage /> },
      { path: 'report', element: <ReportPage /> },
      { path: 'detail', element: <DetailPage /> },
      { path: 'single', element: <SinglePage /> },
      { path: 'about', element: <AboutPage /> },
    ],
  },
])
