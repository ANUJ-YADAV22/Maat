import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Send, ThumbsUp, RotateCcw, Star, Pencil, Wrench, BookOpen, GitBranch, Workflow, Zap, Loader2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { post } from '../api'
import { useApi, useToast } from '../hooks'
import type { Family, GateOutcome, KBEntry, Overview, TaskResp, TaskRow } from '../types'
import { Card, CardHead, PageTitle, SimChip, ago } from '../components/ui'

const FAMILIES: { id: Family; label: string }[] = [
  { id: 'clause_query', label: 'Clause query' }, { id: 'incident_triage', label: 'Incident triage' },
  { id: 'unit_calc', label: 'Unit calc' }, { id: 'safety_checklist', label: 'Safety checklist' },
  { id: 'tender_extract', label: 'Tender extract' },
]

function examples(kb: KBEntry[]): Record<Family, string[]> {
  const clause = kb.filter((e) => e.attribute !== 'severity' && e.domain !== 'tender_docs').slice(-4)
  const sev = kb.filter((e) => e.attribute === 'severity').slice(0, 3)
  const tender = kb.filter((e) => e.domain === 'tender_docs')
  const bySubj = new Map<string, string[]>()
  tender.forEach((e) => bySubj.set(e.subject, [...(bySubj.get(e.subject) ?? []), `${e.attribute}=${e.value}`]))
  const t = [...bySubj.entries()].slice(0, 2).map(([s, kv]) => `Extract the tender fields from: ${s.toUpperCase()}: ${kv.join('; ')}`)
  return {
    clause_query: clause.map((e) => `What is the ${e.attribute} of ${e.subject}?`),
    incident_triage: sev.map((e) => `Site report. What is the severity of ${e.subject}?`),
    unit_calc: ['CONVERT: 2.5 m -> mm', 'COMPUTE: 12*4', 'CONVERT: 12 kn -> n'],
    safety_checklist: ['Prepare the pre-work safety checklist for scaffold work.', 'Prepare the pre-work safety checklist for hot work welding on level 3.'],
    tender_extract: t,
  }
}

export default function Playground() {
  const { data: kb } = useApi<{ entries: KBEntry[] }>('/kb')
  const { data: o } = useApi<Overview>('/overview', 3000)
  const { data: recent, reload: reloadRecent } = useApi<TaskRow[]>('/tasks?limit=8', 4000)
  const toast = useToast()
  const [user, setUser] = useState('you')
  const [family, setFamily] = useState<Family>('clause_query')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [resp, setResp] = useState<TaskResp | null>(null)
  const [edit, setEdit] = useState<string | null>(null)
  const [sent, setSent] = useState<string[]>([])
  const [outcomes, setOutcomes] = useState<GateOutcome[] | null>(null)
  const [running, setRunning] = useState(false)
  const ex = useMemo(() => examples(kb?.entries ?? []), [kb])

  async function ask() {
    if (!text.trim()) return
    setBusy(true); setSent([]); setEdit(null); setOutcomes(null)
    try { setResp(await post<TaskResp>('/task', { user_id: user, family, input: text })); void reloadRecent() }
    catch (e) { toast('bad', (e as Error).message) } finally { setBusy(false) }
  }
  async function fb(signal: string, extra: Record<string, unknown> = {}) {
    if (!resp) return
    try {
      await post('/feedback', { user_id: user, task_id: resp.task_id, signal_type: signal, ...extra })
      setSent((s) => [...s, signal]); toast('ok', `Feedback logged: ${signal}`)
    } catch (e) { toast('bad', (e as Error).message) }
  }
  async function process() {
    setRunning(true)
    try { await post('/proposals/run'); setOutcomes(await post<GateOutcome[]>('/gate/run')) }
    catch (e) { toast('bad', (e as Error).message) } finally { setRunning(false) }
  }
  const t = resp?.trace
  return (
    <>
      <PageTitle title="Playground" sub="Ask the agent, then teach it. Corrections go through the safety gate, never straight into the config." right={<span className="chip gold">answering with config v{resp?.config_version ?? o?.config_version ?? '—'}</span>} />
      <div className="split" style={{ gridTemplateColumns: 'minmax(0,1.5fr) minmax(300px,0.8fr)' }}>
        <div className="col" style={{ gap: 16 }}>
          <Card glow>
            <div className="row wrap" style={{ marginBottom: 14 }}>
              <div className="seg">{FAMILIES.map((f) => <button key={f.id} className={family === f.id ? 'on' : ''} onClick={() => setFamily(f.id)}>{f.label}</button>)}</div>
              <span className="spacer" />
              <input style={{ width: 130 }} value={user} onChange={(e) => setUser(e.target.value)} aria-label="User id" placeholder="user id" />
            </div>
            <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a task, or pick an example below…" onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void ask() }} />
            <div className="row wrap" style={{ marginTop: 10 }}>
              {ex[family].map((q) => <button key={q} className="trace-chip" style={{ cursor: 'pointer' }} onClick={() => setText(q)}>{q.length > 56 ? q.slice(0, 54) + '…' : q}</button>)}
              <span className="spacer" />
              <button className="btn primary" onClick={() => void ask()} disabled={busy || !text.trim()}>{busy ? <Loader2 size={16} className="pulse" /> : <Send size={16} />}Ask agent</button>
            </div>
          </Card>

          <AnimatePresence>
            {resp && (
              <motion.div key={resp.task_id} className="col" style={{ gap: 16 }} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
                <Card>
                  <CardHead title="Agent answer" aside={<span className="chip gold">v{resp.config_version}</span>} />
                  <div className="bubble"><pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'var(--mono)', fontSize: 14 }}>{resp.answer}</pre></div>
                  {t && (
                    <div className="col" style={{ marginTop: 14, gap: 8 }}>
                      <div className="row wrap"><BookOpen size={14} color="var(--ink-3)" />{t.memory_ids.length ? t.memory_ids.map((m) => <span key={m} className="trace-chip">memory {m}</span>) : <span className="faint">no memory used</span>}</div>
                      <div className="row wrap"><Wrench size={14} color="var(--ink-3)" />{t.tool_calls.length ? t.tool_calls.map((c, i) => <span key={i} className="trace-chip">{c.tool}({c.args.join(', ')}) → {JSON.stringify(c.result)}</span>) : <span className="faint">no tools called</span>}</div>
                      <div className="row wrap"><Workflow size={14} color="var(--ink-3)" />{t.workflow_steps.map((s) => <span key={s} className="trace-chip">{s}</span>)}</div>
                      <div className="row wrap"><GitBranch size={14} color="var(--ink-3)" />{t.rule_ids.map((r) => <span key={r} className="trace-chip">rule {r}</span>)}</div>
                    </div>
                  )}
                </Card>
                <Card>
                  <CardHead title="Teach the agent" aside={sent.length > 0 && <span className="chip ok">{sent.join(' · ')}</span>} />
                  <div className="row wrap">
                    <button className="btn ok" onClick={() => void fb('accept')}><ThumbsUp size={16} />Accept</button>
                    <button className="btn" onClick={() => void fb('redo')}><RotateCcw size={16} />Redo</button>
                    <span className="row" style={{ gap: 2 }}>{[1, 2, 3, 4, 5].map((n) => <button key={n} className="btn icon sm" aria-label={`${n} stars`} onClick={() => void fb('rating', { rating: n })}><Star size={15} /></button>)}</span>
                    <button className="btn primary" onClick={() => setEdit(edit === null ? resp.answer : null)}><Pencil size={16} />Correct it</button>
                  </div>
                  <AnimatePresence>
                    {edit !== null && (
                      <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} style={{ overflow: 'hidden' }}>
                        <label className="f" style={{ marginTop: 14 }}>The correct answer</label>
                        <textarea value={edit} onChange={(e) => setEdit(e.target.value)} />
                        <div className="row" style={{ marginTop: 10 }}>
                          <span className="faint" style={{ fontSize: 12 }}>The gate checks this against verified sources before anything changes.</span><span className="spacer" />
                          <button className="btn primary" onClick={() => { void fb('edit', { edit }); setEdit(null) }}>Submit correction</button>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                  {sent.length > 0 && (
                    <div style={{ marginTop: 16 }}>
                      <div className="divider" />
                      {o?.worker ? <span className="muted"><Zap size={14} style={{ verticalAlign: -2 }} /> The background learning loop will pick this up within seconds. <Link to="/patches" style={{ color: 'var(--gold)' }}>Watch patches</Link>.</span> : (
                        <button className="btn" onClick={() => void process()} disabled={running}>{running ? <Loader2 size={16} className="pulse" /> : <Zap size={16} />}Process feedback now</button>
                      )}
                    </div>
                  )}
                  {outcomes && (
                    <div className="col" style={{ marginTop: 14 }}>
                      {outcomes.length === 0 && <span className="muted">Nothing to decide. The feedback did not produce a viable patch (see the audit log).</span>}
                      {outcomes.map((x) => (
                        <Link key={x.patch_id} to={`/patches/${x.patch_id}`} className="bubble row">
                          <span className={`chip ${x.outcome === 'adopt' ? 'ok' : x.outcome === 'reject' ? 'bad' : 'warn'}`}>{x.outcome}</span>
                          <span className="muted" style={{ flex: 1 }}>{x.reasons[0]}</span><span className="mono faint">{x.patch_id}</span>
                        </Link>
                      ))}
                    </div>
                  )}
                </Card>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <div className="col" style={{ gap: 16 }}>
          <Card><CardHead title="Recent tasks" aside={<SimChip />} />
            <div className="col" style={{ gap: 8 }}>
              {(recent ?? []).map((r) => (
                <div key={r.task_id} className="bubble" style={{ padding: '10px 12px', cursor: 'pointer' }} onClick={() => { setFamily(r.family); setText(r.input) }}>
                  <div className="row" style={{ fontSize: 12 }}><span className="chip">{r.family.replace('_', ' ')}</span><span className="spacer" /><span className="faint">v{r.config_version} · {ago(r.ts)}</span></div>
                  <div className="mono" style={{ marginTop: 6, fontSize: 12.5 }}>{r.input.slice(0, 80)}</div>
                  <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>→ {r.answer.split('\n')[0].slice(0, 70)}</div>
                </div>
              ))}
              {recent && recent.length === 0 && <span className="muted">Nothing asked yet.</span>}
            </div>
          </Card>
        </div>
      </div>
    </>
  )
}
