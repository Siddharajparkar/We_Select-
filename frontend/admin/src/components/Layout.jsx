import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext.jsx';

export default function Layout() {
  const { user, tenant, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">W</span>
          <div>
            <div className="brand-name">WeSelect</div>
            <div className="brand-sub">Assessment Platform</div>
          </div>
        </div>
        <nav className="nav">
          <NavLink to="/assessments" end={false} className={({ isActive }) => (isActive ? 'active' : '')}>
            Assessments
          </NavLink>
          {user?.role === 'admin' && (
            <NavLink to="/users" className={({ isActive }) => (isActive ? 'active' : '')}>
              Team &amp; Users
            </NavLink>
          )}
        </nav>
        <div className="sidebar-foot">{tenant?.name}</div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div />
          <div className="topbar-user">
            <div className="who">
              <strong>{user?.name}</strong>
              <span className="role-chip">{user?.role}</span>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={onLogout}>Sign out</button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}