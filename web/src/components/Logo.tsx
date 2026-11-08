export function Logo({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-label="Maat">
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#f7dc92" /><stop offset="1" stopColor="#b9852b" /></linearGradient>
        <radialGradient id="lb" cx="50%" cy="0%" r="90%"><stop offset="0" stopColor="#2a2314" /><stop offset="1" stopColor="#0b0d14" /></radialGradient>
      </defs>
      <rect width="48" height="48" rx="13" fill="url(#lb)" stroke="rgba(233,189,87,.35)" />
      <g fill="none" stroke="url(#lg)" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
        <path d="M24 9.5v27M13 16.5h22M13 16.5l-4.6 9.6h9.2zM35 16.5l-4.6 9.6h9.2zM17.5 38.5h13" />
        <path d="M24 9.5c3.4-.2 5.6 1.6 6.2 4.2" opacity=".8" />
      </g>
      <circle cx="24" cy="9" r="1.6" fill="url(#lg)" />
    </svg>
  )
}
