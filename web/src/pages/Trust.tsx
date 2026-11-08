import { motion } from 'framer-motion'
import { ShieldHalf } from 'lucide-react'
import { useApi } from '../hooks'
import type { Domain, TrustRow } from '../types'
import { Card, Empty, PageTitle, SimChip } from '../components/ui'
import { TrustRing } from '../components/Charts'

const DOMAINS: { id: Domain; label: string }[] = [
  { id: 'structural_codes', label: 'Structural codes' }, { id: 'site_safety', label: 'Site safety' }, { id: 'tender_docs', label: 'Tender documents' },
]

export default function Trust() {
  const { data } = useApi<TrustRow[]>('/trust', 4000)
  return (
    <>
      <PageTitle title="Trust board" sub="Beta posterior per user and domain. Trust lowers the evidence bar. It never skips a lock." right={<SimChip />} />
      {data && data.length === 0 ? <Card><Empty title="No users yet" icon={<ShieldHalf size={34} />}>Trust appears once someone gives feedback.</Empty></Card> : (
        <Card className="flush">
          <table className="t">
            <thead><tr><th>User</th>{DOMAINS.map((d) => <th key={d.id}>{d.label}</th>)}</tr></thead>
            <tbody>
              {(data ?? []).map((r, i) => (
                <motion.tr key={r.user_id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.04 }}>
                  <td><div className="row"><b>{r.user_id}</b>{r.user_id.startsWith('sim_') && <span className="chip sim">simulated</span>}</div></td>
                  {DOMAINS.map((d) => (
                    <td key={d.id}><div className="row"><TrustRing value={r.trust[d.id]} size={52} /><span className="faint" style={{ fontSize: 12 }}>{r.trust[d.id] === 0.5 ? 'no history' : r.trust[d.id] > 0.5 ? 'earned' : 'lost'}</span></div></td>
                  ))}
                </motion.tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      <Card className="tight" delay={0.2}>
        <div className="muted" style={{ fontSize: 13 }}>
          New accounts start at 50 and earn trust slowly (account-age weighting). Wrong claims cost more than right ones earn.
          Trust decays toward neutral over time, and corroboration only counts independent users above 60.
        </div>
      </Card>
    </>
  )
}
