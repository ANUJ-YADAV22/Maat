import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, X, ShieldAlert, PartyPopper } from 'lucide-react'
import { Link } from 'react-router-dom'
import { post } from '../api'
import { useApi, useToast } from '../hooks'
import type { GateOutcome, PatchRow, QueueItem } from '../types'
import { Card, Empty, PageTitle, TierChip, ago } from '../components/ui'

export default function Approvals() {
  const { data: q, reload } = useApi<QueueItem[]>('/queue', 3000)
  const { data: patches } = useApi<PatchRow[]>('/patches', 3000)
  const toast = useToast()
  const [notes, setNotes] = useState<Record<number, string>>({})
  const byId = new Map((patches ?? []).map((p) => [p.patch_id, p]))
  async function act(item: QueueItem, approve: boolean) {
    try {
      const r = await post<GateOutcome>(`/patches/${item.patch_id}/${approve ? 'approve' : 'reject'}`, { reviewer: 'reviewer', reason: notes[item.item_id] || (approve ? 'approved by reviewer' : 'rejected by reviewer') })
      toast(approve ? 'ok' : 'info', approve ? `Adopted as config v${r.config_version}` : 'Rejected and remembered')
      void reload()
    } catch (e) { toast('bad', (e as Error).message) }
  }
  return (
    <>
      <PageTitle title="Human approvals" sub="Claims the system cannot verify on its own wait here for an expert" />
      {q && q.length === 0 ? (
        <Card><Empty title="Nothing waiting" icon={<PartyPopper size={34} />}>Everything has either been proven, refuted, or remembered. Unverifiable claims land here.</Empty></Card>
      ) : (
        <div className="col" style={{ gap: 14 }}>
          <AnimatePresence>
            {(q ?? []).map((item) => {
              const p = byId.get(item.patch_id)
              return (
                <motion.div key={item.item_id} layout initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 60 }}>
                  <Card glow>
                    <div className="row wrap">
                      <ShieldAlert size={20} color="var(--warn)" />
                      <div style={{ flex: 1, minWidth: 260 }}>
                        <div className="display" style={{ fontSize: 22 }}>{p?.claim_text ?? item.patch_id}</div>
                        <div className="muted" style={{ marginTop: 4 }}>{item.reason}</div>
                        <div className="row wrap" style={{ marginTop: 10 }}>{p && <TierChip tier={p.risk_tier} />}{p && <span className="chip">from {p.users.join(', ')}</span>}<span className="faint">queued {ago(item.ts)}</span><Link to={`/patches/${item.patch_id}`} style={{ color: 'var(--gold)' }}>review evidence →</Link></div>
                      </div>
                      <div className="col" style={{ minWidth: 260 }}>
                        <input placeholder="Reviewer note" value={notes[item.item_id] ?? ''} onChange={(e) => setNotes({ ...notes, [item.item_id]: e.target.value })} />
                        <div className="row"><button className="btn ok" style={{ flex: 1, justifyContent: 'center' }} onClick={() => void act(item, true)}><Check size={16} />Approve</button><button className="btn bad" style={{ flex: 1, justifyContent: 'center' }} onClick={() => void act(item, false)}><X size={16} />Reject</button></div>
                      </div>
                    </div>
                  </Card>
                </motion.div>
              )
            })}
          </AnimatePresence>
        </div>
      )}
    </>
  )
}
