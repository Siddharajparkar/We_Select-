import { useState } from 'react';

const LETTERS = ['A', 'B', 'C', 'D'];

export default function QuestionEditor({ initial, onSave, onCancel, saving }) {
  const editing = Boolean(initial);
  const [type, setType] = useState(initial?.type || 'mcq');
  const [body, setBody] = useState(initial?.body || '');
  const [options, setOptions] = useState(
    initial?.options?.length === 4 ? [...initial.options] : ['', '', '', '']
  );
  const [correct, setCorrect] = useState(initial?.correct || 'A');
  const [rubric, setRubric] = useState(initial?.rubric || '');
  const [maxScore, setMaxScore] = useState(initial?.maxScore ?? (initial?.type === 'descriptive' ? 10 : 1));
  const [error, setError] = useState('');

  const isChoice = type === 'mcq' || type === 'cognitive';

  const submit = () => {
    if (!body.trim()) return setError('Question text is required.');
    const ms = Number(maxScore);
    if (!Number.isFinite(ms) || ms <= 0) return setError('Max score must be greater than 0.');
    if (isChoice) {
      if (options.some((o) => !o.trim())) return setError('All four options are required.');
      onSave({ type, body: body.trim(), options: options.map((o) => o.trim()), correct, maxScore: ms });
    } else {
      if (!rubric.trim()) return setError('A scoring rubric is required for descriptive questions.');
      onSave({ type, body: body.trim(), rubric: rubric.trim(), maxScore: ms });
    }
  };

  return (
    <div>
      {!editing && (
        <div className="form-group">
          <label>Question type</label>
          <select
            className="input"
            value={type}
            onChange={(e) => { setType(e.target.value); setMaxScore(e.target.value === 'descriptive' ? 10 : 1); }}
          >
            <option value="mcq">MCQ</option>
            <option value="descriptive">Descriptive</option>
            <option value="cognitive">Cognitive</option>
          </select>
        </div>
      )}
      <div className="form-group">
        <label>Question</label>
        <textarea className="input" rows={3} value={body} onChange={(e) => setBody(e.target.value)} />
      </div>

      {isChoice ? (
        <>
          {LETTERS.map((L, i) => (
            <div className="form-group" key={L}>
              <label>Option {L}</label>
              <input className="input" value={options[i]} onChange={(e) => setOptions((o) => o.map((v, idx) => (idx === i ? e.target.value : v)))} />
            </div>
          ))}
          <div className="form-row">
            <div className="form-group">
              <label>Correct answer</label>
              <select className="input" value={correct} onChange={(e) => setCorrect(e.target.value)}>
                {LETTERS.map((L) => <option key={L} value={L}>{L}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>Marks</label>
              <input className="input" type="number" value={maxScore} onChange={(e) => setMaxScore(e.target.value)} />
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="form-group">
            <label>Scoring rubric</label>
            <textarea className="input" rows={4} value={rubric} onChange={(e) => setRubric(e.target.value)} placeholder="e.g. 4 marks for explaining X, 3 marks for Y, 3 marks for examples" />
          </div>
          <div className="form-group">
            <label>Max score</label>
            <input className="input" type="number" value={maxScore} onChange={(e) => setMaxScore(e.target.value)} />
          </div>
        </>
      )}

      {error && <div className="field-error">{error}</div>}
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        <button className="btn btn-primary" onClick={submit} disabled={saving}>{saving ? 'Saving...' : 'Save question'}</button>
      </div>
    </div>
  );
}
