import { useState } from 'react'
import { motion } from 'framer-motion'
import { Undo2, GitCommitHorizontal, Plus, Minus, Pencil } from 'lucide-react'
import { post } from '../api'
import { useApi, useToast } from '../hooks'
import type { DiffItem, VersionRow } from '../types'
import { Card, CardHead, Modal, PageTitle, ago } from '../components/ui'

const ICON = { added: <Plus size={14} />, removed: <Minus size={14} />, changed: <Pencil size={14} /> }
const CLS = { added: 'diff-add', removed: 'diff-del', changed: 'diff-chg' }

export default function Versions() {
  const { data: v, reload } = useApi<VersionRow[]>('/versions', 4000)
  const [sel, setSel] = useState<number | null>(null)
  const rows = (v ?? []).slice().reverse()
  const cur = sel ?? rows[0]?.version ?? null
  const row = rows.find((r) => r.version === cur)
  const { data: diff } = useApi<DiffItem[]>(row && row.parent ? `/versions/${row.parent}/diff/${row.version}` : null)
  const [modal, setModal] = useState(false)
  const [reason, setReason] = useState('')
  const toast = useToast()
  const latest = rows[0]?.version
  async function rollback() {
    if (!row || !reason.trim()) return
    try {
      const r = await post<{ config_version: number }>('/rollback', { to_version: row.version, reason })
      toast('ok', `Restored v${row.version} as new version v${r.config_version}`)
      setModal(false); setReason(''); setSel(null); void reload()
    } catch (e) { toast('bad', (e as Error).message) }
  }
  return (
    <>
      <PageTitle title="Version history" sub="Every adoption is a new version. Rollback creates a new one; history is never rewritten." />
      <div className="split" style={{ gridTemplateColumns: 'minmax(300px,0.8fr) minmax(0,1.4fr)' }}>
        <Card>
          <CardHead title="Timeline" />
          <div className="timeline">
            {rows.map((r, i) => (
              <motion.div key={r.version} className="tl-item" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                <div className={`dot ${r.stage === 'rollback' ? 'warn' : ''}`}><GitCommitHorizontal size={11} /></div>
                <div className={`listcard ${cur === r.version ? 'sel' : ''}`} onClick={() => setSel(r.version)}>
                  <div className="row"><b className="display" style={{ fontSize: 20 }}>v{r.version}</b>{r.version === latest && <span className="chip ok"><i />active</span>}{r.stage === 'rollback' && <span className="chip gold">rollback</span>}<span className="spacer" /><span className="faint" style={{ fontSize: 12 }}>{ago(r.ts)}</span></div>
                  <div className="muted" style={{ marginTop: 4 }}>{r.claim_text ?? (r.stage === 'rollback' ? r.rollback_note?.headline : 'Initial configuration')}</div>
                  <div className="mono faint" style={{ fontSize: 11, marginTop: 4 }}>{r.config_hash}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </Card>
        <div className="col" style={{ gap: 16 }}>
          {row && (
            <>
              <Card glow>
                <div className="row"><h2 className="display" style={{ fontSize: 28 }}>Version {row.version}</h2><span className="spacer" />
                  {row.version !== latest && <button className="btn primary" onClick={() => setModal(true)}><Undo2 size={16} />Roll back to v{row.version}</button>}</div>
                <dl className="kv" style={{ marginTop: 12 }}>
                  <dt>Parent</dt><dd>{row.parent ? `v${row.parent}` : 'none (initial)'}</dd>
                  <dt>Created from</dt><dd className="mono">{row.created_from_patch ?? '—'}</dd>
                  <dt>Content hash</dt><dd className="mono">{row.config_hash}</dd>
                </dl>
              </Card>
              {row.rollback_note && (
                <Card><CardHead title="Why it was rolled back" /><div className="display" style={{ fontSize: 19, marginBottom: 8 }}>{row.rollback_note.headline}</div>
                  {row.rollback_note.lines.map((l) => <div key={l} className="muted">• {l}</div>)}</Card>
              )}
              <Card>
                <CardHead title={row.parent ? `What changed from v${row.parent}` : 'Initial configuration'} />
                {!row.parent && <span className="muted">The starting memory, rules, tool policy and workflow.</span>}
                {diff && diff.length === 0 && <span className="muted">Identical to its parent: a rollback that restored earlier behaviour.</span>}
                <div className="col" style={{ gap: 12 }}>
                  {(diff ?? []).map((d) => (
                    <div key={d.path} className="bubble">
                      <div className={`row ${CLS[d.change]}`} style={{ marginBottom: 6 }}>{ICON[d.change]}<b className="mono">{d.path}</b><span className="chip">{d.change}</span></div>
                      <div className="grid g2">
                        {d.before !== null && <pre className="code" style={{ borderColor: 'rgba(255,97,115,.25)' }}>{JSON.stringify(d.before, null, 1)}</pre>}
                        {d.after !== null && <pre className="code" style={{ borderColor: 'rgba(63,220,154,.25)' }}>{JSON.stringify(d.after, null, 1)}</pre>}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </>
          )}
        </div>
      </div>
      <Modal open={modal} onClose={() => setModal(false)} title={`Roll back to v${row?.version}`}>
        <p className="muted" style={{ marginTop: 0 }}>This creates a new version that copies v{row?.version}. Later patches are marked rolled back and their tests leave the regression suite.</p>
        <label className="f">Reason (shown in the explanation)</label>
        <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. accept rate dropped after the change" />
        <div className="row" style={{ marginTop: 16, justifyContent: 'flex-end' }}><button className="btn" onClick={() => setModal(false)}>Cancel</button><button className="btn primary" disabled={!reason.trim()} onClick={() => void rollback()}>Roll back</button></div>
      </Modal>
    </>
  )
}
