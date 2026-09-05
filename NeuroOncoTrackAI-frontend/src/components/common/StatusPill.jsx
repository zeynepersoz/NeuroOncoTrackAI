export default function StatusPill({ tone = 'info', children }) {
  return <span className={`status-pill tone-${tone}`}>{children}</span>;
}
