export function Spinner({ label }: { label: string }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        padding: '20px 0',
      }}
    >
      <svg
        width="44"
        height="44"
        viewBox="0 0 44 44"
        fill="none"
        style={{ animation: 'spin .9s linear infinite' }}
      >
        <circle cx="22" cy="22" r="18" stroke="#e2e8f0" strokeWidth="4" />
        <path d="M40 22a18 18 0 0 0-18-18" stroke="#6366f1" strokeWidth="4" strokeLinecap="round" />
      </svg>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a' }}>{label}</div>
        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>Analyzing drawings…</div>
      </div>
    </div>
  );
}
