import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import Badge from '../components/Badge.jsx';
import { Empty, ErrorBox, Loading } from '../components/PageState.jsx';
import { useUi } from '../context/UiContext.jsx';
import { formatDate } from '../utils.js';

export default function AssessmentsPage() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState('');
  const navigate = useNavigate();
  const { toast, confirm } = useUi();

  const load = useCallback(async () => {
    try {
      setError(null);
      setItems(await api.listAssessments(status));
    } catch (e) { setError(e); }
  }, [status]);

  useEffect(() => { setItems(null); load(); }, [load]);

  const stats = useMemo(() => {
    const list = items || [];
    return {
      total: list.length,
      open: list.filter((a) => a.status === 'open').length,
      participants: list.reduce((n, a) => n + (a.participantCount || 0), 0),
      submitted: list.reduce((n, a) => n + (a.submittedCount || 0), 0),
    };
  }, [items]);

  const remove = async (a) => {
    const ok = await confirm({ title: 'Delete assessment', message: `Delete draft "${a.title}"? This cannot be undone.`, confirmText: 'Delete', danger: true });
    if (!ok) return;
    try { await api.deleteAssessment(a.id); toast('Assessment deleted.', 'success'); load(); }
    catch (e) { toast(e.message, 'error'); }
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Assessments</h1>
          <p className="muted">Create, manage and review your candidate assessments.</p>
        </div>
        <Link className="btn btn-primary" to="/assessments/new">+ New assessment</Link>
      </div>

      <div className="stats">
        <div className="stat"><span>Assessments</span><strong>{stats.total}</strong></div>
        <div className="stat"><span>Open</span><strong>{stats.open}</strong></div>
        <div className="stat"><span>Participants</span><strong>{stats.participants}</strong></div>
        <div className="stat"><span>Submitted</span><strong>{stats.submitted}</strong></div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3 className="card-title">All assessments</h3>
          <select className="input input-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="draft">Draft</option>
            <option value="approved">Approved</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>
        </div>

        {error ? <ErrorBox error={error} onRetry={load} />
          : !items ? <Loading />
          : items.length === 0 ? (
            <Empty title="No assessments yet" text="Create your first assessment to get started."
              action={<Link className="btn btn-primary" to="/assessments/new">Create assessment</Link>} />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr><th>Title</th><th>Status</th><th>Participants</th><th>Submitted</th><th>Created</th><th /></tr>
                </thead>
                <tbody>
                  {items.map((a) => (
                    <tr key={a.id} className="clickable" onClick={() => navigate(`/assessments/${a.id}`)}>
                      <td><strong>{a.title}</strong></td>
                      <td><Badge value={a.status} /></td>
                      <td>{a.participantCount ?? 0}</td>
                      <td>{a.submittedCount ?? 0}</td>
                      <td>{formatDate(a.createdAt)}</td>
                      <td className="right" onClick={(e) => e.stopPropagation()}>
                        {a.status === 'draft' && (
                          <button className="btn btn-ghost btn-sm" onClick={() => remove(a)}>Delete</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </div>
    </>
  );
}
