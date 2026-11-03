import { useCallback, useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { api } from '../api.js';
import Badge from '../components/Badge.jsx';
import { Empty, ErrorBox, Loading } from '../components/PageState.jsx';
import { useUi } from '../context/UiContext.jsx';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function ParticipantsTab() {
  const { assessment } = useOutletContext();
  const { toast, confirm } = useUi();
  const approved = assessment.status === 'approved' || assessment.status === 'open';

  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [csv, setCsv] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (silent = false) => {
    try {
      const r = await api.listParticipants(assessment.id);
      setRows(r);
      setError(null);
    } catch (e) { if (!silent) setError(e); }
  }, [assessment.id]);

  useEffect(() => { load(); }, [load]);

  // While invitations are being sent, refresh automatically.
  useEffect(() => {
    if (!rows?.some((r) => r.inviteStatus === 'queued')) return undefined;
    const t = setInterval(() => load(true), 5000);
    return () => clearInterval(t);
  }, [rows, load]);

  const report = (r) => {
    const inv = r.invalid?.length || 0;
    toast(`Added ${r.added}, duplicates ${r.duplicates}, invalid ${inv}.`, r.added > 0 ? 'success' : 'info');
  };

  const addOne = async (e) => {
    e.preventDefault();
    if (!name.trim()) return toast('Enter the participant name.', 'error');
    if (!EMAIL_RE.test(email.trim())) return toast('Enter a valid email address.', 'error');
    setBusy(true);
    try {
      report(await api.addParticipants(assessment.id, { participants: [{ name: name.trim(), email: email.trim() }] }));
      setName(''); setEmail(''); load();
    } catch (err) { toast(err.message, 'error'); }
    finally { setBusy(false); }
  };

  const onCsvFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 1024 * 1024) { toast('CSV file is too large.', 'error'); return; }
    const reader = new FileReader();
    reader.onload = () => setCsv(String(reader.result || ''));
    reader.readAsText(f);
    e.target.value = '';
  };

  const addCsv = async () => {
    let text = csv.trim();
    if (!text) return toast('Paste CSV text or choose a file first.', 'error');
    if (!/^\s*name\s*,\s*email/i.test(text)) text = `name,email\n${text}`;
    setBusy(true);
    try {
      report(await api.addParticipants(assessment.id, { csv: text }));
      setCsv(''); load();
    } catch (err) { toast(err.message, 'error'); }
    finally { setBusy(false); }
  };

  const sendAll = async () => {
    const ok = await confirm({
      title: 'Send invitations',
      message: 'Send assessment invitation emails to all participants who have not been invited yet?',
      confirmText: 'Send emails',
    });
    if (!ok) return;
    setBusy(true);
    try {
      const r = await api.sendInvitations(assessment.id, {});
      toast(`Invitations queued${r?.queued !== undefined ? ` (${r.queued})` : ''}. Emails are being sent.`, 'success');
      load();
    } catch (err) {
      toast(err.code === 'NOT_APPROVED' ? 'Approve the questions before sending invitations.' : err.message, 'error');
    } finally { setBusy(false); }
  };

  const resend = async (p) => {
    try { await api.resend(p.id); toast(`New invitation queued for ${p.email}. The old link no longer works.`, 'success'); load(); }
    catch (err) { toast(err.message, 'error'); }
  };

  const remove = async (p) => {
    const ok = await confirm({ title: 'Remove participant', message: `Remove ${p.email}?`, confirmText: 'Remove', danger: true });
    if (!ok) return;
    try { await api.deleteParticipant(p.id); toast('Participant removed.', 'success'); load(); }
    catch (err) { toast(err.message, 'error'); }
  };

  const started = (p) => p.attemptStatus && p.attemptStatus !== 'none';

  return (
    <>
      <div className="grid-2">
        <form className="card" onSubmit={addOne} noValidate>
          <h3 className="card-title">Add a participant</h3>
          <div className="form-group"><label>Name</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div className="form-group"><label>Email</label><input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <button className="btn btn-primary" disabled={busy}>Add participant</button>
        </form>

        <div className="card">
          <h3 className="card-title">Bulk add (CSV)</h3>
          <p className="muted">One participant per line: <code>name,email</code>. Maximum 200 per assessment.</p>
          <textarea className="input" rows={5} value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={'Asha Rao,asha@example.com\nVikram Shah,vikram@example.com'} />
          <div className="toolbar">
            <input type="file" accept=".csv,text/csv,text/plain" onChange={onCsvFile} />
            <span className="grow" />
            <button className="btn btn-primary" onClick={addCsv} disabled={busy}>Add from CSV</button>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3 className="card-title">Participants {rows ? `(${rows.length})` : ''}</h3>
          <div className="toolbar tight">
            <button className="btn btn-ghost btn-sm" onClick={() => load()}>Refresh</button>
            <button className="btn btn-primary" onClick={sendAll} disabled={busy || !approved || !rows?.length}>Send invitations</button>
          </div>
        </div>
        {!approved && <div className="alert alert-info">Approve the questions first. Invitations can only be sent for approved assessments.</div>}

        {error ? <ErrorBox error={error} onRetry={load} />
          : !rows ? <Loading />
          : rows.length === 0 ? <Empty title="No participants yet" text="Add participants above." />
          : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Name</th><th>Email</th><th>Invitation</th><th>Attempt</th><th>Score</th><th /></tr></thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.id}>
                      <td><strong>{p.name}</strong></td>
                      <td>{p.email}</td>
                      <td><Badge value={p.inviteStatus} /></td>
                      <td><Badge value={p.attemptStatus || 'none'} /></td>
                      <td>{p.percent !== undefined && p.percent !== null ? `${Math.round(p.percent)}%` : '-'}</td>
                      <td className="right">
                        {approved && !started(p) && (p.inviteStatus === 'sent' || p.inviteStatus === 'failed') && (
                          <button className="btn btn-ghost btn-sm" onClick={() => resend(p)}>Resend</button>
                        )}
                        {!started(p) && (
                          <button className="btn btn-ghost btn-sm danger-text" onClick={() => remove(p)}>Remove</button>
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

