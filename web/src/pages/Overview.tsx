import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, Activity, Cpu, Database, Timer, Sparkles, ShieldCheck, Ban, Hourglass } from 'lucide-react'
import { useApi } from '../hooks'
import type { AuditRow, Overview as O, PatchDetail, PatchRow } from '../types'
import { Card, CardHead, CountUp, PageTitle, Skeleton, Stat, SimChip, StatusChip, ago } from '../components/ui'
import { Donut, STATUS_COLOR } from '../components/Charts'
import { LockChain } from '../components/LockChain'
import { Logo } from '../components/Logo'

const EVENT: Record<string, [string, string]> = {
  'feedback.logged': ['Feedback received', 'info'], 'patch.proposed': ['Patch proposed', 'info'],
  'gate.started': ['Safety gate started', 'gold'], 'patch.adopted': ['Patch adopted', 'ok'],
  'patch.rejected': ['Patch rejected', 'bad'], 'patch.quarantined': ['Sent to human review', 'warn'],
  'patch.inconclusive': ['Inconclusive', 'warn'], 'config.rollback': ['Rolled back', 'gold'],
  'trust.updated': ['Trust updated', ''], 'proposal.rejected': ['Proposal not viable', 'warn'],
  'proposal.merged': ['Merged with existing patch', ''], 'config.bootstrap': ['Config v1 loaded', ''],
  'feedback.rejected': ['Feedback refused', 'bad'], 'worker.error': ['Worker error', 'bad'],
}

function Feed({ rows }: { rows: AuditRow[] }) {
  return (
    <div className="col" style={{ gap: 4 }}>
      {rows.map((r, i) => {
        const [label, tone] = EVENT[r.event] ?? [r.event, '']
        const d = r.details_json as Record<string, any>
        const detail = d.patch_id ?? d.user_id ?? d.version ?? ''
        return (
          <motion.div key={r.entry_id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }} className="row" style={{ padding: '8px 0', borderBottom: '1px solid var(--line)' }}>
            <span className={`chip ${tone}`} style={{ minWidth: 168, justifyContent: 'flex-start' }}><i />{label}</span>
            <span className="mono faint" style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{String(detail)}</span>
            <span className="faint" style={{ fontSize: 12 }}>{ago(r.ts)}</span>
          </motion.div>
        )
      })}
    </div>
  )
}

export default function Overview() {
  const { data: o } = useApi<O>('/overview', 3000)
  const { data: patches } = useApi<PatchRow[]>('/patches', 3000)
  const latest = patches && patches.length ? patches[patches.length - 1] : null
  const { data: detail } = useApi<PatchDetail>(latest ? `/patches/${latest.patch_id}` : null, 3000)
  const c = o?.patch_counts ?? {}
  const blocked = (c.rejected ?? 0)
  return (
    <>
      <PageTitle title="Overview" sub="A live view of how the agent learns, and what it refuses to learn" right={o && <>{o.kb_mode === 'real' ? <span className="chip ok"><i />real knowledge base</span> : <span className="chip sim">synthetic DEMO-CODE data</span>}<SimChip /></>} />
      <div className="col" style={{ gap: 16 }}>
        <Card glow className="hero">
          <div className="orb" />
          <div className="scales"><Logo size={74} /></div>
          <h2><span className="gold-text">Learn from feedback.</span> Adopt only what is proven.</h2>
          <p>Every correction becomes a warranted patch. It must be true, fix the problem, keep protected rules, and change nothing else, before a single line of the agent's configuration moves. No retraining. Fully reversible.</p>
          <div className="row">
            <Link to="/scenarios" className="btn primary"><Sparkles size={16} />Run a live scenario<ArrowRight size={16} /></Link>
            <Link to="/playground" className="btn">Try the playground</Link>
          </div>
        </Card>

        <div className="grid g4">
          <Card className="tight" delay={0.05}><Stat label="Active config" value={o ? <span className="gold-text">v{o.config_version}</span> : <Skeleton h={38} w={80} />} detail="memory · rules · tools · workflow" /></Card>
          <Card className="tight" delay={0.1}><Stat color="var(--ok)" label="Adopted" value={o ? <CountUp to={c.adopted ?? 0} /> : <Skeleton h={38} w={60} />} detail={<span className="row" style={{ gap: 6 }}><ShieldCheck size={14} />proven and reversible</span>} /></Card>
          <Card className="tight" delay={0.15}><Stat color="var(--bad)" label="Blocked" value={o ? <CountUp to={blocked} /> : <Skeleton h={38} w={60} />} detail={<span className="row" style={{ gap: 6 }}><Ban size={14} />{o?.rejections_remembered ?? 0} claims remembered</span>} /></Card>
          <Card className="tight" delay={0.2}><Stat color="var(--warn)" label="Awaiting review" value={o ? <CountUp to={o.pending_approvals} /> : <Skeleton h={38} w={60} />} detail={<span className="row" style={{ gap: 6 }}><Hourglass size={14} />needs an expert</span>} /></Card>
        </div>

        <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1.5fr) minmax(0,1fr)' }}>
          <Card delay={0.1}>
            <CardHead title="Latest decision" icon={<Activity size={16} color="var(--gold)" />} aside={latest && <StatusChip status={latest.status} />} />
            {latest && detail ? (
              <>
                <div className="display" style={{ fontSize: 22, marginBottom: 16 }}>{latest.claim_text}</div>
                <LockChain runs={detail.gate_runs} />
                <div style={{ marginTop: 14 }}><Link to={`/patches/${latest.patch_id}`} className="btn sm">Open patch passport<ArrowRight size={14} /></Link></div>
              </>
            ) : <div className="muted" style={{ padding: '30px 0' }}>No patches yet. Give the agent a correction in the playground, or run a live scenario.</div>}
          </Card>
          <Card delay={0.15}>
            <CardHead title="Outcomes" />
            <div className="row" style={{ gap: 22 }}>
              <Donut counts={c} />
              <div className="col" style={{ gap: 8 }}>
                {Object.entries(c).map(([k, v]) => <div key={k} className="row" style={{ gap: 8 }}><i style={{ width: 9, height: 9, borderRadius: 3, background: STATUS_COLOR[k] }} /><span className="muted" style={{ textTransform: 'capitalize' }}>{k.replace('_', ' ')}</span><b style={{ marginLeft: 'auto' }}>{v}</b></div>)}
                {!Object.keys(c).length && <span className="faint">Nothing decided yet</span>}
              </div>
            </div>
          </Card>
        </div>

        <div className="grid g2">
          <Card delay={0.1}><CardHead title="Activity" icon={<Activity size={16} color="var(--gold)" />} />{o ? <Feed rows={o.recent_audit} /> : <Skeleton h={160} />}</Card>
          <Card delay={0.15}>
            <CardHead title="Under the hood" icon={<Cpu size={16} color="var(--gold)" />} />
            <dl className="kv">
              <dt>Model backend</dt><dd>{o?.backend ?? '—'} <span className="faint">(frozen, never retrained)</span></dd>
              <dt>Knowledge base</dt><dd className="row" style={{ gap: 6 }}><Database size={14} />{o?.kb_entries ?? '—'} entries · {o?.kb_mode}</dd>
              <dt>Gate time</dt><dd className="row" style={{ gap: 6 }}><Timer size={14} />{o?.avg_gate_seconds ?? '—'} s per patch, offline</dd>
              <dt>Added to answers</dt><dd><b style={{ color: 'var(--ok)' }}>0 ms</b> <span className="faint">the gate never sits on the user path</span></dd>
              <dt>Replays</dt><dd className="mono">{o?.replays.replays ?? 0} run · {o?.replays.cache_hits ?? 0} cached</dd>
              <dt>Tasks · feedback</dt><dd className="mono">{o?.tasks ?? 0} · {o?.feedback ?? 0}</dd>
            </dl>
          </Card>
        </div>
      </div>
    </>
  )
}
