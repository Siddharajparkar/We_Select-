import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { api, downloadExport } from '../api.js';
import Badge from '../components/Badge.jsx';
import { Empty, ErrorBox, Loading } from '../components/PageState.jsx';
import { useUi } from '../context/UiContext.jsx';
import { fmtNum, formatDuration } from '../utils.js';

export default function ResultsTab() {
  const { assessment } = useOutletContext();
  const navigate = useNavigate();
  const { toast } = useUi();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [sort, setSort] = useState('score');
  const [exporting, setExporting] = useState('');

  const load = useCallback(async () => {
    try { setError(null); setData(await api.results(assessment.id, sort)); }
    catch (e) { setError(e); }
  }, [assessment.id, sort]);

  useEffect(() => { setData(null); load(); }, [load]);

  const exportAs = async (format) => {
    setExporting(format);
    try { await downloadExport(assessment.id, format); toast(`${format.toUpperCase()} downloaded.`, 'success'); }
    catch (e) { toast(e.message, 'error'); }
    finally { setExporting(''); }
  };

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!data) return <Loading />;

  const { summary, rows } = data;

  return (
    <>
      <div className="stats">
        <div className="stat"><span>Candidates</span><strong>{summary?.count ?? 0}</strong></div>
        <div className="stat"><span>Average score</span><strong>{summary?.avg !== undefined ? `${fmtNum(summary.avg)}%` : '-'}</strong></div>
        <div className="stat"><span>Pass rate</span><strong>{summary?.passRate !== undefined ? `${fmtNum(summary.passRate <= 1 ? summary.passRate * 100 : summary.passRate, 0)}%` : '-'}</strong></div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3 className="card-title">Candidate results</h3>
          <div className="toolbar tight">
            <select className="input input-auto" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="score">Sort by score</option>
              <option value="name">Sort by name</option>
            </select>
            <button className="btn btn-outline btn-sm" onClick={() => exportAs('csv')} disabled={Boolean(exporting)}>{exporting === 'csv' ? 'Preparing...' : 'Export CSV'}</button>
            <button className="btn btn-outline btn-sm" onClick={() => exportAs('pdf')} disabled={Boolean(exporting)}>{exporting === 'pdf' ? 'Preparing...' : 'Export PDF'}</button>
          </div>
        </div>

        {!rows || rows.length === 0 ? (
          <Empty title="No results yet" text="Results appear here once candidates submit their attempts." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>#</th><th>Candidate</th><th>Score</th><th>Percent</th><th>Result</th><th>Time taken</th><th>Status</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.attemptId} className="clickable" onClick={() => navigate(`/attempts/${r.attemptId}`)}>
                    <td>{i + 1}</td>
                    <td><strong>{r.name}</strong><div className="muted small">{r.email}</div></td>
                    <td>{fmtNum(r.score)} / {fmtNum(r.maxScore)}</td>
                    <td><strong>{fmtNum(r.percent)}%</strong></td>
                    <td><span className={`badge ${r.passed ? 'b-open' : 'b-failed'}`}>{r.passed ? 'Passed' : 'Not passed'}</span></td>
                    <td>{formatDuration(r.timeTakenSec)}</td>
                    <td><Badge value={r.status} /></td>
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


