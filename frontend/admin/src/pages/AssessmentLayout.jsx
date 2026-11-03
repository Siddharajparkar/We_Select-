import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api.js';
import Badge from '../components/Badge.jsx';
import { ErrorBox, Loading } from '../components/PageState.jsx';
import { useUi } from '../context/UiContext.jsx';

export default function AssessmentLayout() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast, confirm } = useUi();
  const [assessment, setAssessment] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const a = await api.getAssessment(id);
      setAssessment(a);
      setError(null);
    } catch (e) { setError(e); }
  }, [id]);

  useEffect(() => { setAssessment(null); load(); }, [load]);

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!assessment) return <Loading />;

  const closeAssessment = async () => {
    const ok = await confirm({
      title: 'Close assessment',
      message: 'No new attempts will be allowed and invitations will expire. Continue?',
      confirmText: 'Close assessment', danger: true,
    });
    if (!ok) return;
    try { await api.closeAssessment(id); toast('Assessment closed.', 'success'); load(); }
    catch (e) { toast(e.message, 'error'); }
  };

  const tab = ({ isActive }) => (isActive ? 'tab active' : 'tab');

  return (
    <>
      <button className="link-back" onClick={() => navigate('/assessments')}>&larr; All assessments</button>
      <div className="page-header">
        <div>
          <h1>{assessment.title}</h1>
          <div className="meta-line">
            <Badge value={assessment.status} />
            <span className="muted">{assessment.durationMinutes} min &middot; pass {assessment.passingScore}%</span>
          </div>
        </div>
        {(assessment.status === 'approved' || assessment.status === 'open') && (
          <button className="btn btn-outline" onClick={closeAssessment}>Close assessment</button>
        )}
      </div>

      <div className="tabs">
        <NavLink end to={`/assessments/${id}`} className={tab}>Overview</NavLink>
        <NavLink to={`/assessments/${id}/questions`} className={tab}>Questions</NavLink>
        <NavLink to={`/assessments/${id}/participants`} className={tab}>Participants</NavLink>
        <NavLink to={`/assessments/${id}/results`} className={tab}>Results</NavLink>
      </div>

      <Outlet context={{ assessment, reload: load }} />
    </>
  );
}

