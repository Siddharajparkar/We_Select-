import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { api } from '../api.js';
import AssessmentForm from '../components/AssessmentForm.jsx';
import { TYPE_LABEL, wordCount } from '../utils.js';
import { useUi } from '../context/UiContext.jsx';

export default function OverviewTab() {
  const { assessment, reload } = useOutletContext();
  const { toast } = useUi();
  const [saving, setSaving] = useState(false);
  const [formKey, setFormKey] = useState(0);

  if (assessment.status !== 'draft') {
    return (
      <div className="card">
        <h3 className="card-title">Assessment details</h3>
        <p className="muted">This assessment is {assessment.status}, so its settings can no longer be edited.</p>
        <dl className="details">
          <dt>Duration</dt><dd>{assessment.durationMinutes} minutes</dd>
          <dt>Passing score</dt><dd>{assessment.passingScore}%</dd>
          <dt>Sections</dt>
          <dd>
            {(assessment.sections || []).map((s, i) => (
              <div key={i}>{TYPE_LABEL[s.type] || s.type} &middot; {s.domain} &middot; {s.difficulty} &middot; {s.count} questions</div>
            ))}
          </dd>
          <dt>Job description</dt>
          <dd>{wordCount(assessment.jobDescription)} words{assessment.jdFileName ? ` (file: ${assessment.jdFileName})` : ''}</dd>
        </dl>
        <pre className="jd-box">{assessment.jobDescription}</pre>
      </div>
    );
  }

  const onSubmit = async (values, file) => {
    setSaving(true);
    try {
      await api.updateAssessment(assessment.id, values);
      if (file) await api.uploadJd(assessment.id, file);
      toast('Assessment saved.', 'success');
      await reload();
      setFormKey((k) => k + 1);
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      setSaving(false);
    }
  };

  return <AssessmentForm key={formKey} initial={assessment} onSubmit={onSubmit} submitLabel="Save changes" saving={saving} />;
}
