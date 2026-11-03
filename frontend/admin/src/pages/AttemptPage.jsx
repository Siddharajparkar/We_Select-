import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api.js';
import Badge from '../components/Badge.jsx';
import Modal from '../components/Modal.jsx';
import { ErrorBox, Loading } from '../components/PageState.jsx';
import { useUi } from '../context/UiContext.jsx';
import { TYPE_LABEL, fmtNum } from '../utils.js';

export default function AttemptPage() {
  const { attemptId } = useParams();
  const navigate = useNavigate();
  const { toast } = useUi();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [target, setTarget] = useState(null);
  const [score, setScore] = useState('');
  const [comment, setComment] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try { setError(null); setData(await api.getAttempt(attemptId)); }
    catch (e) { setError(e); }
  }, [attemptId]);

  useEffect(() => { load(); }, [load]);

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!data) return <Loading />;

  const answers = data.answers || [];
  const total = answers.reduce((a, x) => a + (Number(x.score) || 0), 0);
  const max = answers.reduce((a, x) => a + (Number(x.maxScore) || 0), 0);

  const openOverride = (a) => { setTarget(a); setScore(String(a.score ?? 0)); setComment(''); };

  const saveOverride = async () => {
    const s = Number(score);
    if (!Number.isFinite(s) || s < 0 || s > Number(target.maxScore)) {
      return toast(`Score must be between 0 and ${target.maxScore}.`, 'error');
    }
    if (!comment.trim()) return toast('Please add a comment explaining the change.', 'error');
    setSaving(true);
    try {
      await api.override(attemptId, target.questionId, { score: s, comment: comment.trim() });
      toast('Score updated.', 'success');
      setTarget(null);
      load();
    } catch (e) { toast(e.message, 'error'); }
    finally { setSaving(false); }
  };

  return (
    <>
      <button className="link-back" onClick={() => navigate(-1)}>&larr; Back to results</button>
      <div className="page-header">
        <div>
          <h1>{data.participant?.name || 'Candidate'}</h1>
          <p className="muted">{data.participant?.email}</p>
        </div>
        <div className="score-pill">
          <span>Total</span>
          <strong>{fmtNum(total)} / {fmtNum(max)}</strong>
        </div>
      </div>

      {answers.map((a, i) => (
        <div className="card qcard" key={a.questionId}>
          <div className="qhead">
            <div className="qmeta">
              <span className="qnum">Q{i + 1}</span>
              <span className="badge b-approved">{TYPE_LABEL[a.type] || a.type}</span>
              <span className="badge b-none">scored by {a.source}</span>
              {a.type !== 'descriptive' && a.correct !== undefined && (
                <span className={`badge ${String(a.answer) === String(a.correct) ? 'b-open' : 'b-failed'}`}>
                  {String(a.answer) === String(a.correct) ? 'Correct' : 'Incorrect'}
                </span>
              )}
            </div>
            <div className="qactions">
              <strong>{fmtNum(a.score)} / {fmtNum(a.maxScore)}</strong>
              <button className="btn btn-ghost btn-sm" onClick={() => openOverride(a)}>Override</button>
            </div>
          </div>
          <p className="qbody">{a.body}</p>
          <div className="answer-box">
            <div className="label">Candidate answer</div>
            <div>{a.answer ? a.answer : <em className="muted">No answer given</em>}</div>
          </div>
          {a.type !== 'descriptive' && a.correct && <div className="muted small">Correct answer: {a.correct}</div>}
          {a.justification && (
            <div className="answer-box ai">
              <div className="label">{a.source === 'manual' ? 'Reviewer comment' : 'AI justification'}</div>
              <div>{a.justification}</div>
            </div>
          )}
          {a.status === 'pending_review' && <Badge value="needs_review" />}
        </div>
      ))}

      {target && (
        <Modal
          title="Override score"
          onClose={() => setTarget(null)}
          footer={<>
            <button className="btn btn-ghost" onClick={() => setTarget(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={saveOverride} disabled={saving}>{saving ? 'Saving...' : 'Save score'}</button>
          </>}
        >
          <p className="muted">The original AI score is kept in the audit log.</p>
          <div className="form-group">
            <label>New score (0 to {target.maxScore})</label>
            <input className="input" type="number" step="0.5" value={score} onChange={(e) => setScore(e.target.value)} />
          </div>
          <div className="form-group">
            <label>Comment (required)</label>
            <textarea className="input" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </Modal>
      )}
    </>
  );
}


