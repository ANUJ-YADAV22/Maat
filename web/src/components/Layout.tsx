import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { LayoutDashboard, MessageSquareText, GitPullRequest, History, ShieldHalf, ShieldAlert, Clapperboard, BookMarked, FlaskConical, ScrollText } from 'lucide-react'
import { Logo } from './Logo'
import { useApi } from '../hooks'
import type { Overview } from '../types'

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Overview', end: true },
  { to: '/scenarios', icon: Clapperboard, label: 'Live scenarios' },
  { to: '/playground', icon: MessageSquareText, label: 'Playground' },
  { to: '/patches', icon: GitPullRequest, label: 'Patches' },
  { to: '/approvals', icon: ShieldAlert, label: 'Approvals', alert: true },
  { to: '/versions', icon: History, label: 'Versions' },
  { to: '/trust', icon: ShieldHalf, label: 'Trust board' },
  { to: '/knowledge', icon: BookMarked, label: 'Knowledge' },
  { to: '/evaluation', icon: FlaskConical, label: 'Evaluation' },
  { to: '/audit', icon: ScrollText, label: 'Audit log' },
]

export function Layout() {
  const { data: o } = useApi<Overview>('/overview', 3000)
  const loc = useLocation()
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><Logo size={42} /><div><b className="gold-text">Maat</b><small>Warranted learning</small></div></div>
        <nav className="nav">
          <div className="nav-label">Workspace</div>
          {NAV.map(({ to, icon: Icon, label, end, alert }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => (isActive ? 'active' : '')}>
              <Icon size={18} /><span className="label">{label}</span>
              {alert && o && o.pending_approvals > 0 && <span className="count alert">{o.pending_approvals}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          <div className="row" style={{ justifyContent: 'space-between' }}><span className="faint">Active config</span><b className="gold-text">v{o?.config_version ?? '—'}</b></div>
          <div className="row" style={{ justifyContent: 'space-between', marginTop: 6 }}><span className="faint">Backend</span><span>{o?.backend ?? '—'}</span></div>
          <div className="row" style={{ justifyContent: 'space-between', marginTop: 6 }}><span className="faint">Learning loop</span><span className="row" style={{ gap: 6 }}><i className={o?.worker ? 'pulse' : ''} style={{ width: 7, height: 7, borderRadius: 9, background: o?.worker ? 'var(--ok)' : 'var(--ink-3)', display: 'inline-block' }} />{o?.worker ? 'live' : 'manual'}</span></div>
        </div>
      </aside>
      <main className="main">
        <AnimatePresence mode="wait">
          <motion.div key={loc.pathname} className="page" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.28 }}>
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  )
}
