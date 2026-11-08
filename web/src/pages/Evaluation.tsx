import { useMemo } from 'react'
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { FlaskConical, Terminal } from 'lucide-react'
import { useApi } from '../hooks'
import type { EvalSummary } from '../types'
import { Card, CardHead, Empty, PageTitle, SimChip, Skeleton } from '../components/ui'

const COLORS: Record<string, string> = { S0: '#8b93a8', S1: '#ff6173', S2: '#ffb54a', S3: '#c9a3ff', S4: '#7aa2ff', S5: '#e9bd57' }
const axis = { stroke: '#6f768c', fontSize: 12 }
const tip = { contentStyle: { background: '#0e1018', border: '1px solid rgba(255,255,255,.13)', borderRadius: 12 }, labelStyle: { color: '#aab0c2' } }

export default function Evaluation() {
  const { data: s, loading } = useApi<EvalSummary>('/eval/summary', 10000)
  const curve = useMemo(() => {
    if (!s?.improvement) return []
    return s.improvement.rounds.map((r, i) => {
      const row: Record<string, number | number[]> = { round: r }
      for (const [id, p] of Object.entries(s.improvement!.series)) {
        row[id] = p.mean[i]
        row[`${id}_band`] = [p.mean[i] - p.se[i], p.mean[i] + p.se[i]]
      }
      return row
    })
  }, [s])
  if (loading) return <><PageTitle title="Evaluation" /><Skeleton h={300} /></>
  if (!s?.available) {
    return (
      <>
        <PageTitle title="Evaluation" sub="Held-out success, attack resistance and ablations across six systems" />
        <Card><Empty title="No evaluation run yet" icon={<FlaskConical size={34} />}>
          Charts here come only from real runs of the harness, never from mock-ups.<br />
          <span className="row" style={{ justifyContent: 'center', marginTop: 14 }}><Terminal size={16} /><span className="mono">make eval-smoke</span></span>
        </Empty></Card>
      </>
    )
  }
  const ids = Object.keys(s.improvement?.series ?? {})
  const names = Object.fromEntries((s.systems ?? []).map((x) => [x.id, x.name]))
  const abl = Object.entries(s.ablation ?? {}).map(([name, v]) => ({ name, v }))
  return (
    <>
      <PageTitle title="Evaluation" sub={`${s.seeds} seeds · ${s.rounds} rounds · backend: ${s.backend}`} right={<>{s.simulated && <SimChip />}<span className="chip">mean ± standard error</span></>} />
      <div className="col" style={{ gap: 16 }}>
        <Card glow>
          <CardHead title="Held-out success vs feedback rounds" />
          <div style={{ height: 340 }}>
            <ResponsiveContainer>
              <ComposedChart data={curve}>
                <CartesianGrid stroke="rgba(255,255,255,.06)" vertical={false} />
                <XAxis dataKey="round" {...axis} /><YAxis domain={[0, 1]} {...axis} /><Tooltip {...tip} /><Legend />
                {ids.map((id) => <Area key={`${id}b`} dataKey={`${id}_band`} stroke="none" fill={COLORS[id]} fillOpacity={0.12} legendType="none" tooltipType="none" />)}
                {ids.map((id) => <Line key={id} dataKey={id} name={`${id} ${names[id] ?? ''}`} stroke={COLORS[id]} strokeWidth={id === 'S5' ? 3 : 1.8} dot={false} />)}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <div className="grid g2">
          <Card className="flush">
            <div style={{ padding: '20px 20px 6px' }}><CardHead title="Attack table (adversarial users)" /></div>
            <table className="t">
              <thead><tr><th>System</th><th>Bad-patch acceptance</th><th>Regression rate</th></tr></thead>
              <tbody>
                {Object.entries(s.attack ?? {}).map(([id, a]) => (
                  <tr key={id}><td><b style={{ color: COLORS[id] }}>{id}</b> <span className="faint">{names[id]}</span></td>
                    <td className="mono">{a.bad_patch_acceptance.mean.toFixed(3)} <span className="faint">± {a.bad_patch_acceptance.se.toFixed(3)}</span></td>
                    <td className="mono">{a.regression_rate.mean.toFixed(3)} <span className="faint">± {a.regression_rate.se.toFixed(3)}</span></td></tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card>
            <CardHead title="Ablation: held-out success when a lock is removed" />
            <div style={{ height: 250 }}>
              <ResponsiveContainer>
                <BarChart data={abl} layout="vertical" margin={{ left: 40 }}>
                  <CartesianGrid stroke="rgba(255,255,255,.06)" horizontal={false} />
                  <XAxis type="number" domain={[0, 1]} {...axis} /><YAxis type="category" dataKey="name" width={130} {...axis} /><Tooltip {...tip} />
                  <Bar dataKey="v" fill="#e9bd57" radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
        {s.far_frr && s.far_frr.length > 0 && (
          <Card>
            <CardHead title="False-accept vs false-reject (threshold sweep)" />
            <div style={{ height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={s.far_frr}>
                  <CartesianGrid stroke="rgba(255,255,255,.06)" vertical={false} />
                  <XAxis dataKey="threshold" {...axis} /><YAxis domain={[0, 1]} {...axis} /><Tooltip {...tip} /><Legend />
                  <Line dataKey="far" name="false accept" stroke="#ff6173" strokeWidth={2.4} dot={false} />
                  <Line dataKey="frr" name="false reject" stroke="#7aa2ff" strokeWidth={2.4} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        )}
        {s.notes?.map((n) => <div key={n} className="faint" style={{ fontSize: 12.5 }}>• {n}</div>)}
      </div>
    </>
  )
}
