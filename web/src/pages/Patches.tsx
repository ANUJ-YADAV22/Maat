import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { GitPullRequest, FileCode2, Check, X, Users } from 'lucide-react'
import { post } from '../api'
import { useApi, useToast } from '../hooks'
import type { Explain, GateOutcome, Passport, PatchDetail, PatchRow, Status } from '../types'
import { Card, CardHead, Empty, PageTitle, Skeleton, StatusChip, TierChip, ago } from '../components/ui'
import { LockChain } from '../components/LockChain'
import { DecisionMetrics, ExplainBlock, PassportCard } from '../components/PatchViews'

const FILTERS: (Status | 'all')[] = ['all', 'adopted', 'rejected', 'quarantined', 'inconclusive', 'rolled_back', 'proposed']
const TYPE_LABEL: Record<string, string> = { memory_note: 'memory', instruction_rule: 'rule', tool_policy: 'tool policy', workflow_step: 'workflow step' }

function Detail({ id }: { id: string }) {
  const { data: d, reload } = useApi<PatchDetail>(`/patches/${id}`, 3000)
  const { data: e } = useApi<Explain>(`/explain/${id}`, 3000)
  const { data: p } = useApi<Passport>(`/passport/${id}`, 3000)
  const toast = useToast()
  const [note, setNote] = useState('')
  if (!d) return <Card><Skeleton h={30} w="60%" /><div style={{ height: 14 }} /><Skeleton h={120} /></Card>
  const c = d.contract
  async function review(approve: boolean) {
    try {
      const r = await post<GateOutcome>(`/patches/${id}/${approve ? 'approve' : 'reject'}`, { reviewer: 'reviewer', reason: note || (approve ? 'approved by reviewer' : 'rejected by reviewer') })
      toast(approve ? 'ok' : 'info', approve ? `Adopted as config v${r.config_version}` : 'Patch rejected and remembered')
      void reload()
    } catch (err) { toast('bad', (err as Error).message) }
  }
  return (
    <div className="col" style={{ gap: 16 }}>
      <Card glow>
        <div className="row wrap" style={{ marginBottom: 10 }}>
          <StatusChip status={d.status} /><TierChip tier={c.risk_tier} /><span className="chip">{TYPE_LABEL[c.type]}</span>
          <span className="chip"><Users size={12} />{c.provenance.feedback_ids.length} event(s)</span>
          <span className="spacer" /><span className="mono faint">{id}</span>
        </div>
        <div className="display" style={{ fontSize: 28, lineHeight: 1.15, marginBottom: 20 }}>{e?.claim ?? '…'}</div>
        <LockChain runs={d.gate_runs} />
      </Card>
      {d.status === 'quarantined' && (
        <Card className="tight" delay={0.05}>
          <div className="row wrap">
            <b style={{ color: 'var(--warn)' }}>Waiting for an expert</b>
            <input style={{ flex: 1, minWidth: 220 }} placeholder="Reviewer note (optional)" value={note} onChange={(ev) => setNote(ev.target.value)} />
            <button className="btn ok" onClick={() => void review(true)}><Check size={16} />Approve</button>
            <button className="btn bad" onClick={() => void review(false)}><X size={16} />Reject</button>
          </div>
        </Card>
      )}
      <Card delay={0.05}><DecisionMetrics runs={d.gate_runs} />{!d.gate_runs.some((r) => r.lock === 'decision') && <span className="muted">No decision yet.</span>}</Card>
      <div className="grid g2">
        {p && <PassportCard p={p} />}
        {e && <Card delay={0.1}><ExplainBlock e={e} /></Card>}
      </div>
      <Card delay={0.1}>
        <CardHead title="Contract" icon={<FileCode2 size={16} color="var(--gold)" />} aside={<span className="faint">proposed by {c.provenance.proposer}</span>} />
        <div className="grid g2">
          <div><label className="f">Operations</label><pre className="code">{JSON.stringify(c.ops, null, 2)}</pre></div>
          <div className="col">
            <div><label className="f">Witness test</label><pre className="code">{JSON.stringify(c.witness_test, null, 2)}</pre></div>
            <div><label className="f">Declared scope</label><pre className="code">{JSON.stringify(c.declared_scope, null, 2)}</pre></div>
          </div>
        </div>
      </Card>
    </div>
  )
}

export default function Patches() {
  const { id } = useParams()
  const nav = useNavigate()
  const { data: rows, loading } = useApi<PatchRow[]>('/patches', 3000)
  const [filter, setFilter] = useState<Status | 'all'>('all')
  const list = (rows ?? []).filter((r) => filter === 'all' || r.status === filter).slice().reverse()
  const count = (s: Status | 'all') => (rows ?? []).filter((r) => s === 'all' || r.status === s).length
  const sel = id ?? list[0]?.patch_id
  return (
    <>
      <PageTitle title="Patches" sub="Every change the agent considered, with the evidence for each decision" right={
        <div className="seg">{FILTERS.map((f) => <button key={f} className={filter === f ? 'on' : ''} onClick={() => setFilter(f)}>{f.replace('_', ' ')} {count(f) ? `· ${count(f)}` : ''}</button>)}</div>} />
      {loading ? <Skeleton h={200} /> : !rows?.length ? (
        <Card><Empty title="No patches yet" icon={<GitPullRequest size={34} />}>Give the agent feedback in the playground, or run a live scenario.</Empty></Card>
      ) : (
        <div className="split">
          <div className="col" style={{ gap: 10, position: 'sticky', top: 90, maxHeight: 'calc(100vh - 110px)', overflow: 'auto', paddingRight: 4 }}>
            {list.map((r, i) => (
              <motion.div key={r.patch_id} className={`listcard ${sel === r.patch_id ? 'sel' : ''}`} onClick={() => nav(`/patches/${r.patch_id}`)} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}>
                <div className="row" style={{ marginBottom: 6 }}><StatusChip status={r.status} /><TierChip tier={r.risk_tier} /><span className="spacer" /><span className="faint" style={{ fontSize: 12 }}>{ago(r.created_ts)}</span></div>
                <div style={{ fontWeight: 600 }}>{r.claim_text}</div>
                <div className="faint" style={{ fontSize: 12, marginTop: 4 }}>{TYPE_LABEL[r.type]} · by {r.users.join(', ') || r.proposer}</div>
              </motion.div>
            ))}
            {!list.length && <div className="muted">No patches with this status.</div>}
          </div>
          <div>{sel && <Detail key={sel} id={sel} />}</div>
        </div>
      )}
    </>
  )
}
