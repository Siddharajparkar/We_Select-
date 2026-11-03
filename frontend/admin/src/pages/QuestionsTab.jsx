import { useCallback, useEffect, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { api, waitForJob } from '../api.js';
import Modal from '../components/Modal.jsx';
import QuestionEditor from '../components/QuestionEditor.jsx';
import { Empty, ErrorBox, Loading } from '../components/PageState.jsx';
import { useUi } from '../context/UiContext.jsx';
import { TYPE_LABEL, wordCount } from '../utils.js';

export default function QuestionsTab() {
  const { assessment, reload } = useOutletContext();
  const { toast, confirm } = useUi();
  const draft = assessment.status === 'draft';

  const [questions, setQuestions] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState('');
  const [editing, setEditing] = useState(null);   // question being edited
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const q = await api.listQuestions(assessment.id);
      setQuestions([...q].sort((a, b) => (a.position ?? 0) - (b.position ?? 0)));
      setError(null);
    } catch (e) { setError(e); }
  }, [assessment.id]);

  useEffect(() => { load(); }, [load]);

  const runJob = async (start, label, okMsg) => {
    setBusy(label);
    try {
      const { jobId } = await start();
      await waitForJob(jobId);
      toast(okMsg, 'success');
      await load();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setBusy('');
    }
  };

  const generate = () => {
    const words = wordCount(assessment.jobDescription);
    if (words < 100) {
      return toast('The job description needs at least 100 words. Edit it on the Overview tab first.', 'error');
    }
    runJob(() => api.generate(assessment.id, {}), 'Generating questions with AI. This can take up to a minute...', 'Questions generated. Please review them.');
  };

  const regenerate = async (q) => {
    const ok = await confirm({ title: 'Regenerate question', message: 'Replace this question with a new AI-generated one?', confirmText: 'Regenerate' });
    if (!ok) return;
    runJob(() => api.regenerateQuestion(q.id), 'Regenerating question...', 'Question regenerated.');
  };

  const remove = async (q) => {
    const ok = await confirm({ title: 'Remove question', message: 'Remove this question permanently?', confirmText: 'Remove', danger: true });
    if (!ok) return;
    try { await api.deleteQuestion(q.id); toast('Question removed.', 'success'); load(); }
    catch (e) { toast(e.message, 'error'); }
  };

  const saveEdit = async (payload) => {
    setSaving(true);
    try { await api.updateQuestion(editing.id, payload); toast('Question updated.', 'success'); setEditing(null); load(); }
    catch (e) { toast(e.message, 'error'); }
    finally { setSaving(false); }
  };

  const saveNew = async (payload) => {
    setSaving(true);
    try { await api.addQuestion(assessment.id, payload); toast('Custom question added.', 'success'); setAdding(false); load(); }
    catch (e) { toast(e.message, 'error'); }
    finally { setSaving(false); }
  };

  const approve = async () => {
    const ok = await confirm({
      title: 'Approve questions',
      message: 'After approval the questions become read-only and you can invite participants. Continue?',
      confirmText: 'Approve',
    });
    if (!ok) return;
    try {
      await api.approve(assessment.id);
      toast('Assessment approved. You can now invite participants.', 'success');
      await reload();
      await load();
    } catch (e) {
      const map = { NO_QUESTIONS: 'Add at least one question before approving.', SECTION_INCOMPLETE: 'Every section needs its questions before approval.' };
      toast(map[e.code] || e.message, 'error');
    }
  };

  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!questions) return <Loading />;

  return (
    <>
      {busy && (
        <div className="alert alert-info"><div className="spinner spinner-sm" /> {busy}</div>
      )}

      {draft && (
        <div className="toolbar">
          <button className="btn btn-primary" onClick={generate} disabled={Boolean(busy)}>
            {questions.length ? 'Generate more with AI' : 'Generate questions with AI'}
          </button>
          <button className="btn btn-outline" onClick={() => setAdding(true)} disabled={Boolean(busy)}>+ Add custom question</button>
          <span className="grow" />
          <button className="btn btn-success" onClick={approve} disabled={Boolean(busy) || questions.length === 0}>Approve all &amp; continue</button>
        </div>
      )}

      {questions.length === 0 ? (
        <div className="card">
          <Empty title="No questions yet" text={draft ? 'Generate questions with AI or add your own.' : 'This assessment has no questions.'} />
        </div>
      ) : (
        questions.map((q, i) => (
          <div className="card qcard" key={q.id}>
            <div className="qhead">
              <div className="qmeta">
                <span className="qnum">Q{i + 1}</span>
                <span className="badge b-approved">{TYPE_LABEL[q.type] || q.type}</span>
                <span className={`badge ${q.source === 'custom' ? 'b-open' : 'b-none'}`}>{q.source === 'custom' ? 'Custom' : 'AI'}</span>
                <span className="muted">{q.maxScore} {q.maxScore === 1 ? 'mark' : 'marks'}</span>
              </div>
              {draft && (
                <div className="qactions">
                  <button className="btn btn-ghost btn-sm" disabled={Boolean(busy)} onClick={() => setEditing(q)}>Edit</button>
                  {q.source !== 'custom' && (
                    <button className="btn btn-ghost btn-sm" disabled={Boolean(busy)} onClick={() => regenerate(q)}>Regenerate</button>
                  )}
                  <button className="btn btn-ghost btn-sm danger-text" disabled={Boolean(busy)} onClick={() => remove(q)}>Remove</button>
                </div>
              )}
            </div>
            <p className="qbody">{q.body}</p>
            {q.options?.length > 0 && (
              <ol className="qoptions" type="A">
                {q.options.map((o, idx) => {
                  const letter = 'ABCD'[idx];
                  const right = q.correct === letter;
                  return <li key={idx} className={right ? 'correct' : ''}>{o}{right && <span className="tick"> &#10003; correct</span>}</li>;
                })}
              </ol>
            )}
            {q.rubric && <div className="rubric"><strong>Rubric:</strong> {q.rubric}</div>}
          </div>
        ))
      )}

      {editing && (
        <Modal title="Edit question" onClose={() => setEditing(null)}>
          <QuestionEditor initial={editing} onSave={saveEdit} onCancel={() => setEditing(null)} saving={saving} />
        </Modal>
      )}
      {adding && (
        <Modal title="Add custom question" onClose={() => setAdding(false)}>
          <QuestionEditor onSave={saveNew} onCancel={() => setAdding(false)} saving={saving} />
        </Modal>
      )}
    </>
  );
}