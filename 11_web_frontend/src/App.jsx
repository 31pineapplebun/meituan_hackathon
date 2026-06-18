import { NavLink, Outlet } from 'react-router-dom'
import styles from './App.module.css'

const STEPS = [
  { to: '/config', label: '① 配置' },
  { to: '/run', label: '② 运行' },
  { to: '/report', label: '③ 报告' },
  { to: '/detail', label: '详查' },
  { to: '/single', label: '单通质检' },
  { to: '/about', label: '关于' },
]

export default function App() {
  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.logo}>🎯</span>
          <div>
            <div className={styles.title}>外呼指令遵循评测</div>
            <div className={styles.subtitle}>React + FastAPI · 取代 Streamlit</div>
          </div>
        </div>
        <nav className={styles.nav}>
          {STEPS.map((s) => (
            <NavLink
              key={s.to}
              to={s.to}
              className={({ isActive }) =>
                isActive ? `${styles.navItem} ${styles.active}` : styles.navItem
              }
            >
              {s.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}
