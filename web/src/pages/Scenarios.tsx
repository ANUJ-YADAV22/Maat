import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, XCircle, TriangleAlert, Info, Play, RotateCcw, Loader2, ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { post } from '../api'
import { useApi, useToast } from '../hooks'
import type { Overview, ScenarioResult, ScenarioStep } from '../types'
import { Card, PageTitle, SimChip } from '../components/ui'
import { ExplainBlock, PassportCard } from '../components/PatchViews'

const BLURB: Record<number, [string, string]> = {
  1: ['Valid correction', 'An expert fixes a wrong answer with a KB-backed claim. It clears every lock and the next answer improves.'],
  2: ['Wrong correction', 'A novice contradicts the verified source. Rejected at Lock 2 before any replay; trust drops and the claim is remembered.'],
  3: ['Invariant attack', '"Skip the harness check." It looks plausible and passes its own test, but the protected-rule veto rejects it absolutely.'],
  4: ['Silent regression', 'A plausible patch fixes one answer and quietly changes others. Lock 5 catches the undeclared impact.'],
  5: ['Conflict', 'Two groups propose opposite values. Both are gated on the same suites; the higher decision margin wins, the loser is explained.'],
  6: ['Rollback', 'A reviewer reverts a change. A new version restores the old behaviour and a generated note explains why.'],
  7: ['Tool-policy patch', 'One "redo" click and no typing. Blame localization finds that clause answers must come from the lookup tool.'],
  8: ['Workflow-step patch', 'A unit conversion is corrected. Blame localization inserts a verify_units step before the final answer.'],
}
const ICON = { ok: CheckCircle2, bad: XCircle, warn: TriangleAlert, info: Info }

function Step({ s, i }: { s: ScenarioStep; i: number }) {
  const Icon = ICON[s.status]
  return (
    <motion.div className="tl-item" initial={{ opacity: 0, x: -14 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.35 * i, duration: 0.4 }}>
      <div className={`dot ${s.status}`}><Icon size={12} /></div>
      <div style={{ fontWeight: 600 }}>{s.title}</div>
      <div className="muted mono" style={{ fontSize: 12.5, marginTop: 2 }}>{s.detail}</div>
    </motion.div>
  )
}

export default function Scenarios() {
  const { data: o } = useApi<Overview>('/overview')
  const toast = useToast()
  const [busy, setBusy] = useState<number | null>(null)
  const [res, setRes] = useState<ScenarioResult | null>(null)
  const [key, setKey] = useState(0)

  async function run(id: number) {
    setBusy(id)
    try {
      setRes(await post<ScenarioResult>(`/demo/scenarios/${id}/run`))
      setKey((k) => k + 1)
    } catch (e) {
      toast('bad', (e as Error).message)
    } finally { setBusy(null) }
  }
  async function reset() {
    try { await post('/demo/reset'); setRes(null); toast('ok', 'Demo state cleared. Config is back to v1.') } catch (e) { toast('bad', (e as Error).message) }
  }
  const off = o && !o.demo_mode
  return (
    <>
      <PageTitle title="Live scenarios" sub="Real code, real gate, simulated users. Pick one and watch the decision unfold." right={<><SimChip /><button className="btn sm" onClick={reset} disabled={!!off}><RotateCcw size={14} />Reset demo</button></>} />
      {off && <Card className="tight" ><b>Demo mode is off.</b> <span className="muted">Start with <span className="mono">make demo</span> (or set MAAT_DEMO_MODE=1) to run scenarios live. Each run resets state first.</span></Card>}
      <div className="grid g4" style={{ marginTop: 16 }}>
        {Object.entries(BLURB).map(([id, [title, text]], i) => (
          <motion.div key={id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
            <div className="card scn" style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 10 }} onClick={() => !off && !busy && void run(Number(id))}>
              <span className="num">{id}</span>
              <h3 className="display" style={{ fontSize: 19, paddingRight: 30 }}>{title}</h3>
              <p className="muted" style={{ margin: 0, fontSize: 13, flex: 1 }}>{text}</p>
              <button className="btn sm primary" disabled={!!off || busy !== null} style={{ alignSelf: 'flex-start' }}>
                {busy === Number(id) ? <Loader2 size={14} className="pulse" /> : <Play size={14} />}{busy === Number(id) ? 'Running' : 'Run'}
              </button>
            </div>
          </motion.div>
        ))}
      </div>
      <AnimatePresence mode="wait">
        {res && (
          <motion.div key={key} className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', marginTop: 18 }} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <Card glow>
              <div className="row" style={{ marginBottom: 6 }}><h2 className="display" style={{ fontSize: 26 }}>{res.id}. {res.title}</h2><span className="spacer" /><SimChip /></div>
              <p className="muted" style={{ marginTop: 0 }}>{res.summary}</p>
              <div className="timeline" style={{ marginTop: 18 }}>{res.steps.map((s, i) => <Step key={i} s={s} i={i} />)}</div>
              <div className="row" style={{ marginTop: 6 }}>
                <span className="chip gold">config v{res.config_version}</span>
                {res.patch_id && <Link to={`/patches/${res.patch_id}`} className="btn sm">Open the full patch<ArrowRight size={14} /></Link>}
              </div>
            </Card>
            <div className="col" style={{ gap: 16 }}>
              {res.passport && <PassportCard p={res.passport} />}
              {res.explanation && <Card><ExplainBlock e={res.explanation} /></Card>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
