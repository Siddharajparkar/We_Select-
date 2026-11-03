import { useCallback, useEffect, useState } from 'react';
import { api } from '../api.js';
import Badge from '../components/Badge.jsx';
import Modal from '../components/Modal.jsx';
import { ErrorBox, Loading } from '../components/PageState.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { useUi } from '../context/UiContext.jsx';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function UsersPage() {
  const { user: me } = useAuth();
  const { toast } = useUi();
  const [users, setUsers] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', role: 'recruiter', password: '' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try { setError(null); setUsers(await api.listUsers()); } catch (e) { setError(e); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.name.trim()) return toast('Name is required.', 'error');
    if (!EMAIL_RE.test(form.email.trim())) return toast('Enter a valid email.', 'error');
    if (form.password.length < 8) return toast('Password must be at least 8 characters.', 'error');
    setSaving(true);
    try {
      await api.createUser({ ...form, name: form.name.trim(), email: form.email.trim() });
      toast('User created.', 'success');
      setOpen(false);
      setForm({ name: '', email: '', role: 'recruiter', password: '' });
      load();
    } catch (e) {
      toast(e.code === 'EMAIL_EXISTS' ? 'A user with this email already exists.' : e.message, 'error');
    } finally { setSaving(false); }
  };

  const patch = async (u, body) => {
    try { await api.updateUser(u.id, body); toast('User updated.', 'success'); load(); }
    catch (e) { toast(e.message, 'error'); }
  };

  return (
    <>
      <div className="page-header">
        <div><h1>Team &amp; Users</h1><p className="muted">Manage who can access your workspace.</p></div>
        <button className="btn btn-primary" onClick={() => setOpen(true)}>+ Add user</button>
      </div>

      <div className="card">
        {error ? <ErrorBox error={error} onRetry={load} /> : !users ? <Loading /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th /></tr></thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td><strong>{u.name}</strong>{u.id === me.id && <span className="muted"> (you)</span>}</td>
                    <td>{u.email}</td>
                    <td>
                      <select className="input input-auto" value={u.role} disabled={u.id === me.id} onChange={(e) => patch(u, { role: e.target.value })}>
                        <option value="admin">Admin</option>
                        <option value="recruiter">Recruiter</option>
                      </select>
                    </td>
                    <td><Badge value={u.status} /></td>
                    <td className="right">
                      {u.id !== me.id && (
                        <button className="btn btn-ghost btn-sm" onClick={() => patch(u, { status: u.status === 'active' ? 'disabled' : 'active' })}>
                          {u.status === 'active' ? 'Disable' : 'Enable'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {open && (
        <Modal title="Add user" onClose={() => setOpen(false)}
          footer={<>
            <button className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
            <button className="btn btn-primary" onClick={create} disabled={saving}>{saving ? 'Creating...' : 'Create user'}</button>
          </>}>
          <div className="form-group"><label>Name</label><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div className="form-group"><label>Email</label><input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
          <div className="form-group"><label>Role</label>
            <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="recruiter">Recruiter</option><option value="admin">Admin</option>
            </select>
          </div>
          <div className="form-group"><label>Temporary password</label><input className="input" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
        </Modal>
      )}
    </>
  );
}

