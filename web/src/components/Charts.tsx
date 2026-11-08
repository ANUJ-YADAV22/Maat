import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import type { Status } from '../types'

export const STATUS_COLOR: Record<string, string> = {
  adopted: '#3fdc9a', rejected: '#ff6173', quarantined: '#ffb54a', inconclusive: '#c9a3ff',
  proposed: '#7aa2ff', gating: '#7aa2ff', rolled_back: '#e9bd57', expired: '#6f768c',
}

export function Donut({ counts, size = 190 }: { counts: Partial<Record<Status, number>>; size?: number }) {
  const data = Object.entries(counts).filter(([, v]) => (v ?? 0) > 0).map(([k, v]) => ({ name: k, value: v as number }))
  const total = data.reduce((a, b) => a + b.value, 0)
  const shown = data.length ? data : [{ name: 'none', value: 1 }]
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <ResponsiveContainer>
        <PieChart>
          <Pie data={shown} dataKey="value" innerRadius="68%" outerRadius="96%" paddingAngle={data.length > 1 ? 3 : 0} stroke="none" startAngle={90} endAngle={-270} animationDuration={900}>
            {shown.map((d) => <Cell key={d.name} fill={STATUS_COLOR[d.name] ?? 'rgba(255,255,255,.08)'} />)}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', textAlign: 'center', pointerEvents: 'none' }}>
        <div><div className="display" style={{ fontSize: 34, lineHeight: 1 }}>{total}</div><div className="faint" style={{ fontSize: 11, letterSpacing: '.1em', textTransform: 'uppercase' }}>decisions</div></div>
      </div>
    </div>
  )
}

export function TrustRing({ value, size = 64 }: { value: number; size?: number }) {
  const r = size / 2 - 6, c = 2 * Math.PI * r
  const col = value >= 0.6 ? '#3fdc9a' : value >= 0.4 ? '#e9bd57' : '#ff6173'
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="rgba(255,255,255,.08)" strokeWidth="5" fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={col} strokeWidth="5" fill="none" strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - value)} style={{ transition: 'stroke-dashoffset .9s ease', filter: `drop-shadow(0 0 6px ${col})` }} />
      </svg>
      <span>{Math.round(value * 100)}</span>
    </div>
  )
}
