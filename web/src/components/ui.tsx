import { motion, AnimatePresence } from 'framer-motion'
import clsx from 'clsx'
import { X, Inbox } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { Status, Tier } from '../types'

export function Card({ children, className, glow, delay = 0 }: { children: ReactNode; className?: string; glow?: boolean; delay?: number }) {
  return (
    <motion.section className={clsx('card', glow && 'glow', className)} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay, ease: [0.22, 1, 0.36, 1] }}>
      {children}
    </motion.section>
  )
}

export function CardHead({ title, icon, aside }: { title: string; icon?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="card-h">
      {icon}<h3>{title}</h3>{aside && <div className="aside">{aside}</div>}
    </div>
  )
}

const STATUS_STYLE: Record<Status, string> = {
  proposed: 'info', gating: 'info', adopted: 'ok', rejected: 'bad', quarantined: 'warn',
  inconclusive: 'warn', rolled_back: 'gold', expired: '',
}
export function StatusChip({ status }: { status: Status }) {
  return <span className={clsx('chip', STATUS_STYLE[status])}><i />{status.replace('_', ' ')}</span>
}
export function TierChip({ tier }: { tier: Tier }) {
  return <span className={clsx('chip', tier === 'high' ? 'bad' : tier === 'medium' ? 'warn' : 'ok')}>{tier} risk</span>
}
export const SimChip = () => <span className="chip sim">simulated</span>

export function Stat({ value, label, detail, color }: { value: ReactNode; label: string; detail?: ReactNode; color?: string }) {
  return (
    <div className="stat">
      <div className="v" style={color ? { color } : undefined}>{value}</div>
      <div className="l">{label}</div>
      {detail && <div className="d">{detail}</div>}
    </div>
  )
}

export function CountUp({ to, decimals = 0, suffix = '' }: { to: number; decimals?: number; suffix?: string }) {
  const [v, setV] = useState(0)
  useEffect(() => {
    const start = performance.now(), dur = 900
    let raf = 0
    const step = (t: number) => {
      const p = Math.min(1, (t - start) / dur)
      setV(to * (1 - Math.pow(1 - p, 3)))
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [to])
  return <>{v.toFixed(decimals)}{suffix}</>
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="empty">
      {icon ?? <Inbox size={34} />}
      <h3 className="display" style={{ fontSize: 20, color: 'var(--ink)', marginBottom: 6 }}>{title}</h3>
      <div>{children}</div>
    </div>
  )
}

export function Skeleton({ h = 18, w = '100%' }: { h?: number; w?: number | string }) {
  return <div className="skeleton" style={{ height: h, width: w }} />
}

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="modal-back" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div className="card modal glow" initial={{ y: 24, scale: 0.97 }} animate={{ y: 0, scale: 1 }} exit={{ y: 12, opacity: 0 }} onClick={(e) => e.stopPropagation()}>
            <div className="card-h"><h3 className="display" style={{ fontSize: 20, textTransform: 'none', letterSpacing: 0, color: 'var(--ink)' }}>{title}</h3><button className="btn icon sm aside" onClick={onClose} aria-label="Close"><X size={16} /></button></div>
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function Meter({ value, max, mark, color }: { value: number; max: number; mark?: number; color?: string }) {
  const pct = (x: number) => `${Math.max(0, Math.min(100, (x / max) * 100))}%`
  return (
    <div className="meter">
      <motion.div className="fill" style={color ? { background: color } : undefined} initial={{ width: 0 }} animate={{ width: pct(value) }} transition={{ duration: 0.9, ease: 'easeOut' }} />
      {mark !== undefined && <div className="mark" style={{ left: pct(mark) }} title={`bar ${mark.toFixed(3)}`} />}
    </div>
  )
}

export function PageTitle({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="topbar">
      <div><h1>{title}</h1>{sub && <div className="sub">{sub}</div>}</div>
      <div className="right">{right}</div>
    </div>
  )
}

export const fmt = (n: number | null | undefined, d = 3) => (n === null || n === undefined ? '—' : n.toFixed(d))
export const ago = (iso: string) => {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${Math.floor(s)}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
