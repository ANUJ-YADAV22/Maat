import { motion } from 'framer-motion'
import { Eye, Scale, FlaskConical, ShieldCheck, Radar, Gavel, Lock, Check, X, Hourglass, Minus } from 'lucide-react'
import { useState } from 'react'
import type { GateRun } from '../types'

const LOCKS = [
  { id: 'screen', title: 'Screen', icon: Eye, q: 'Safe to consider?' },
  { id: 'warrant', title: 'Warrant', icon: Scale, q: 'Is the claim true?' },
  { id: 'witness', title: 'Witness', icon: FlaskConical, q: 'Does it fix the problem?' },
  { id: 'invariants', title: 'Invariants', icon: ShieldCheck, q: 'Protected rules intact?' },
  { id: 'impact', title: 'Impact', icon: Radar, q: 'Changed only what it declared?' },
  { id: 'decision', title: 'Decision', icon: Gavel, q: 'Does gain beat risk?' },
] as const

function Mark({ s }: { s: string }) {
  if (s === 'pass' || s === 'adopt') return <Check size={22} strokeWidth={3} />
  if (s === 'fail' || s === 'reject') return <X size={22} strokeWidth={3} />
  if (s === 'quarantine' || s === 'inconclusive') return <Hourglass size={20} />
  return <Minus size={18} />
}

export function LockChain({ runs }: { runs: GateRun[] }) {
  const byLock = Object.fromEntries(runs.map((r) => [r.lock, r]))
  const [open, setOpen] = useState<string | null>(null)
  const reached = LOCKS.filter((l) => byLock[l.id]).length
  const sel = open ? byLock[open] : null
  return (
    <div>
      <div className="chain">
        <div className="rail"><motion.i initial={{ width: 0 }} animate={{ width: `${Math.max(0, (reached - 1) / 5) * 100}%` }} transition={{ duration: 1.1, ease: 'easeInOut' }} /></div>
        {LOCKS.map((l, i) => {
          const run = byLock[l.id]
          const s = run ? run.result : 'skipped'
          const Icon = l.icon
          return (
            <motion.div key={l.id} className={`link ${s}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 * i, duration: 0.4 }} onClick={() => run && setOpen(open === l.id ? null : l.id)}>
              <div className="node">{run ? <Mark s={s} /> : <Icon size={20} />}</div>
              <div className="t">{i + 1}. {l.title}</div>
              <div className="s">{run ? s : 'not reached'}</div>
            </motion.div>
          )
        })}
      </div>
      {sel ? (
        <motion.div key={sel.lock} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="bubble" style={{ marginTop: 14 }}>
          <div className="row" style={{ marginBottom: 6 }}><Lock size={14} color="var(--gold)" /><b>{LOCKS.find((l) => l.id === sel.lock)?.title}</b><span className="faint">{LOCKS.find((l) => l.id === sel.lock)?.q}</span></div>
          {sel.reasons_json.map((r, i) => <div key={i} className="muted">• {r}</div>)}
        </motion.div>
      ) : (
        <div className="faint" style={{ marginTop: 12, fontSize: 12 }}>Select a lock to see why it decided as it did.</div>
      )}
    </div>
  )
}
