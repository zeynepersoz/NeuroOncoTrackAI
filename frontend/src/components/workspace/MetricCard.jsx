export default function MetricCard({ icon: Icon, label, value, detail, tone = 'info' }) {
  return (
    <article className={`product-metric tone-${tone}`}>
      <span aria-hidden="true">
        <Icon size={18} />
      </span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
        <em>{detail}</em>
      </div>
    </article>
  );
}
