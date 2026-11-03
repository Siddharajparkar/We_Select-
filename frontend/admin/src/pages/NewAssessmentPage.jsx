import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import AssessmentForm from '../components/AssessmentForm.jsx';
import { useUi } from '../context/UiContext.jsx';

export default function NewAssessmentPage() {
  const navigate = useNavigate();
  const { toast } = useUi();
  const [saving, setSaving] = useState(false);

  const onSubmit = async (values, file) => {
    setSaving(true);
    let created;
    try {
      created = await api.createAssessment(values);
    } catch (e) {
      toast(e.message, 'error');
      setSaving(false);
      return;
    }
    if (file) {
      try {
        await api.uploadJd(created.id, file);
      } catch (e) {
        toast(`Assessment created, but the file upload failed: ${e.message}`, 'error');
      }
    }
    toast('Assessment created. Now generate questions.', 'success');
    navigate(`/assessments/${created.id}/questions`);
  };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>New assessment</h1>
          <p className="muted">Describe the role. AI will draft questions that you can review and edit.</p>
        </div>
      </div>
      <AssessmentForm onSubmit={onSubmit} submitLabel="Create assessment" saving={saving} />
    </>
  );
}
