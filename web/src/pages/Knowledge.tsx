import { useMemo, useState } from 'react'
import { BadgeCheck, Search, AlertTriangle } from 'lucide-react'
import { useApi } from '../hooks'
import type { Domain, KBEntry } from '../types'
import { Card, PageTitle, Skeleton } from '../components/ui'

export default function Knowledge() {
  const { data } = useApi<{ mode: 'synthetic' | 'real'; entries: KBEntry[] }>('/kb')
  const [q, setQ] = useState('')
  const [dom, setDom] = useState<Domain | 'all'>('all')
  const rows = useMemo(() => (data?.entries ?? []).filter((e) => (dom === 'all' || e.domain === dom) && `${e.subject} ${e.attribute} ${e.source_doc} ${e.quote ?? ''}`.toLowerCase().includes(q.toLowerCase())), [data, q, dom])
  return (
    <>
      <PageTitle title="Knowledge base" sub="The verifier behind Lock 2. Every fact carries its source and who verified it." right={data && (data.mode === 'real' ? <span className="chip ok"><i />real documents</span> : <span className="chip sim">synthetic DEMO-CODE</span>)} />
      {data?.mode === 'synthetic' && (
        <Card className="tight"><div className="row"><AlertTriangle size={18} color="var(--warn)" /><span className="muted">These values are made up so the demo never states real engineering numbers. Set <span className="mono">MAAT_KB_MODE=real</span> and load verified facts with <span className="mono">scripts/ingest_kb.py</span>.</span></div></Card>
      )}
      <Card className="flush">
        <div className="row wrap" style={{ padding: 16 }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 240 }}><Search size={15} style={{ position: 'absolute', left: 12, top: 13, color: 'var(--ink-3)' }} /><input style={{ paddingLeft: 36 }} placeholder="Search subject, attribute, source or quote" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <div className="seg">{(['all', 'structural_codes', 'site_safety', 'tender_docs'] as const).map((d) => <button key={d} className={dom === d ? 'on' : ''} onClick={() => setDom(d)}>{d.replace('_', ' ')}</button>)}</div>
        </div>
        {!data ? <div style={{ padding: 16 }}><Skeleton h={160} /></div> : (
          <div style={{ maxHeight: '62vh', overflow: 'auto' }}>
            <table className="t">
              <thead><tr><th>Subject</th><th>Attribute</th><th>Value</th><th>Source</th><th>Verified</th></tr></thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id}>
                    <td className="mono">{e.subject}<div className="faint" style={{ fontSize: 11, fontFamily: 'var(--sans)' }}>{e.domain.replace('_', ' ')}</div></td>
                    <td className="mono">{e.attribute}</td>
                    <td><b>{String(e.value)}</b> <span className="faint">{e.unit}</span></td>
                    <td>{e.source_doc} <span className="faint">§{e.section}{e.page ? ` · p.${e.page}` : ''}</span>{e.quote && <div className="faint" style={{ fontSize: 12, marginTop: 2, maxWidth: 420 }}>“{e.quote}”</div>}</td>
                    <td>{e.verified ? <span className="chip ok"><BadgeCheck size={12} />{e.verified_by}</span> : <span className="chip warn">unverified</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!rows.length && <div className="empty">No entries match.</div>}
          </div>
        )}
      </Card>
    </>
  )
}
