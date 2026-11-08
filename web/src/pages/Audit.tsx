import { Fragment, useMemo, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { useApi } from '../hooks'
import type { AuditRow } from '../types'
import { Card, PageTitle, Skeleton, ago } from '../components/ui'

export default function Audit() {
  const { data } = useApi<AuditRow[]>('/audit?limit=300', 3000)
  const [open, setOpen] = useState<number | null>(null)
  const [f, setF] = useState('')
  const events = useMemo(() => [...new Set((data ?? []).map((r) => r.event))].sort(), [data])
  const rows = (data ?? []).filter((r) => !f || r.event === f)
  return (
    <>
      <PageTitle title="Audit log" sub="Every state change, who made it, and why" right={<select style={{ width: 210 }} value={f} onChange={(e) => setF(e.target.value)}><option value="">All events</option>{events.map((e) => <option key={e}>{e}</option>)}</select>} />
      <Card className="flush">
        {!data ? <div style={{ padding: 16 }}><Skeleton h={200} /></div> : (
          <table className="t">
            <thead><tr><th style={{ width: 30 }} /><th>Event</th><th>Actor</th><th>Details</th><th>When</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <Fragment key={r.entry_id}>
                  <tr style={{ cursor: 'pointer' }} onClick={() => setOpen(open === r.entry_id ? null : r.entry_id)}>
                    <td><ChevronRight size={14} style={{ transform: open === r.entry_id ? 'rotate(90deg)' : undefined, transition: '.15s' }} /></td>
                    <td><span className="chip gold">{r.event}</span></td><td>{r.actor}</td>
                    <td className="mono faint" style={{ maxWidth: 460, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{JSON.stringify(r.details_json)}</td>
                    <td className="faint">{ago(r.ts)}</td>
                  </tr>
                  {open === r.entry_id && <tr><td /><td colSpan={4}><pre className="code">{JSON.stringify(r.details_json, null, 2)}</pre></td></tr>}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  )
}
