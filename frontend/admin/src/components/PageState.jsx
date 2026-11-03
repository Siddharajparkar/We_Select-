export function Loading({ full = false, text = 'Loading...' }) {
  return (
    <div className={full ? 'state state-full' : 'state'}>
      <div className="spinner" />
      <p>{text}</p>
    </div>
  );
}

export function ErrorBox({ error, onRetry }) {
  return (
    <div className="state">
      <div className="state-icon">!</div>
      <p>{error?.message || 'Something went wrong. Please try again.'}</p>
      {onRetry && <button className="btn btn-primary" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Empty({ title, text, action }) {
  return (
    <div className="state">
      <div className="state-icon state-icon-soft">&#9776;</div>
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {action}
    </div>
  );
}
