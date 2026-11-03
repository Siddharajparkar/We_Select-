import { useState } from 'react';
import { wordCount } from '../utils.js';

const newSection = () => ({ type: 'mcq', domain: '', difficulty: 'medium', count: 5 });

export default function AssessmentForm({ initial, onSubmit, submitLabel, saving }) {
  const [title, setTitle] = useState(initial?.title || '');
  const [durationMinutes, setDuration] = useState(initial?.durationMinutes ?? 60);
  const [passingScore, setPassing] = useState(initial?.passingScore ?? 60);
  const [jobDescription, setJd] = useState(initial?.jobDescription || '');
  const [sections, setSections] = useState(
    initial?.sections?.length ? initial.sections.map((s) => ({ ...s })) : [newSection()]
  );
  const [file, setFile] = useState(null);
  const [errors, setErrors] = useState({});

  const words = wordCount(jobDescription);
  const total = sections.reduce((a, s) => a + (Number(s.count) || 0), 0);

  const updateSection = (i, patch) =>
    setSections((arr) => arr.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));

  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return setFile(null);
    const ok = /\.(pdf|txt)$/i.test(f.name);
    if (!ok) { setErrors((er) => ({ ...er, file: 'Only .pdf or .txt files are allowed.' })); e.target.value = ''; return; }
    if (f.size > 2 * 1024 * 1024) { setErrors((er) => ({ ...er, file: 'File must be 2 MB or smaller.' })); e.target.value = ''; return; }
    setErrors((er) => ({ ...er, file: undefined }));
    setFile(f);
  };

  const validate = () => {
    const er = {};
    if (!title.trim()) er.title = 'Title is required.';
    const d = Number(durationMinutes);
    if (!Number.isFinite(d) || d < 1 || d > 480) er.duration = 'Enter 1 to 480 minutes.';
    const p = Number(passingScore);
    if (!Number.isFinite(p) || p < 0 || p > 100) er.passing = 'Enter a percentage from 0 to 100.';
    if (jobDescription.length > 20000) er.jd = 'Job description is limited to 20,000 characters.';
    if (!sections.length) er.sections = 'Add at least one section.';
    sections.forEach((s, i) => {
      if (!s.domain.trim()) er[`domain${i}`] = 'Required';
      const c = Number(s.count);
      if (!Number.isInteger(c) || c < 1 || c > 20) er[`count${i}`] = '1 to 20';
    });
    if (total > 40) er.sections = 'Total questions cannot exceed 40.';
    setErrors(er);
    return Object.keys(er).length === 0;
  };

  const submit = (e) => {
    e.preventDefault();
    if (!validate()) return;
    onSubmit(
      {
        title: title.trim(),
        jobDescription,
        durationMinutes: Number(durationMinutes),
        passingScore: Number(passingScore),
        sections: sections.map((s) => ({
          type: s.type,
          domain: s.domain.trim(),
          difficulty: s.difficulty,
          count: Number(s.count),
        })),
      },
      file
    );
  };

  return (
    <form onSubmit={submit} noValidate>
      <div className="card">
        <h3 className="card-title">Basic information</h3>
        <div className="form-group">
          <label>Assessment title</label>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Backend Engineer Screening" maxLength={200} />
          {errors.title && <div className="field-error">{errors.title}</div>}
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>Duration (minutes)</label>
            <input className="input" type="number" value={durationMinutes} onChange={(e) => setDuration(e.target.value)} />
            {errors.duration && <div className="field-error">{errors.duration}</div>}
          </div>
          <div className="form-group">
            <label>Passing score (%)</label>
            <input className="input" type="number" value={passingScore} onChange={(e) => setPassing(e.target.value)} />
            {errors.passing && <div className="field-error">{errors.passing}</div>}
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="card-title">Job description</h3>
        <p className="muted">Paste the job description, or upload a PDF/TXT file (max 2 MB). At least 100 words are needed to generate questions.</p>
        <div className="form-group">
          <textarea className="input" rows={9} value={jobDescription} onChange={(e) => setJd(e.target.value)} placeholder="Paste the full job description here..." />
          <div className={`hint ${words > 0 && words < 100 ? 'hint-warn' : ''}`}>
            {words} words &middot; {jobDescription.length}/20000 characters
            {words > 0 && words < 100 ? ' (needs at least 100 words)' : ''}
          </div>
          {errors.jd && <div className="field-error">{errors.jd}</div>}
        </div>
        <div className="form-group">
          <label>Or upload a file</label>
          <input type="file" accept=".pdf,.txt" onChange={onFile} />
          {initial?.jdFileName && !file && <div className="hint">Current file: {initial.jdFileName}</div>}
          {file && <div className="hint">Selected: {file.name}. Its extracted text will replace the pasted text.</div>}
          {errors.file && <div className="field-error">{errors.file}</div>}
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3 className="card-title">Question sections</h3>
          <span className="muted">Total: {total} / 40</span>
        </div>
        {sections.map((s, i) => (
          <div className="section-row" key={i}>
            <div className="form-group">
              <label>Type</label>
              <select className="input" value={s.type} onChange={(e) => updateSection(i, { type: e.target.value })}>
                <option value="mcq">MCQ</option>
                <option value="descriptive">Descriptive</option>
                <option value="cognitive">Cognitive</option>
              </select>
            </div>
            <div className="form-group grow">
              <label>Domain / topic</label>
              <input className="input" value={s.domain} onChange={(e) => updateSection(i, { domain: e.target.value })} placeholder="e.g. Node.js" />
              {errors[`domain${i}`] && <div className="field-error">{errors[`domain${i}`]}</div>}
            </div>
            <div className="form-group">
              <label>Difficulty</label>
              <select className="input" value={s.difficulty} onChange={(e) => updateSection(i, { difficulty: e.target.value })}>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </div>
            <div className="form-group narrow">
              <label>Count</label>
              <input className="input" type="number" value={s.count} onChange={(e) => updateSection(i, { count: e.target.value })} />
              {errors[`count${i}`] && <div className="field-error">{errors[`count${i}`]}</div>}
            </div>
            <button type="button" className="btn btn-ghost btn-sm remove-btn" disabled={sections.length === 1} onClick={() => setSections((a) => a.filter((_, idx) => idx !== i))}>
              Remove
            </button>
          </div>
        ))}
        {errors.sections && <div className="field-error">{errors.sections}</div>}
        <button type="button" className="btn btn-outline" onClick={() => setSections((a) => [...a, newSection()])}>
          + Add section
        </button>
      </div>

      <div className="form-actions">
        <button className="btn btn-primary" disabled={saving}>{saving ? 'Saving...' : submitLabel}</button>
      </div>
    </form>
  );
}