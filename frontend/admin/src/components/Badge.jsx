export default function Badge({ value }) {
  const v = value || 'none';
  return <span className={`badge b-${v}`}>{String(v).replace(/_/g, ' ')}</span>;
}