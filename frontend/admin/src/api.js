const BASE = '/api/v1';

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function extractMessage(data, status) {
  if (data?.error?.message) return data.error.message;
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) {
    return data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
  }
  return `Request failed (${status})`;
}

async function request(path, { method = 'GET', body, formData } = {}) {
  const opts = { method, credentials: 'same-origin', headers: {} };
  if (formData) {
    opts.body = formData;
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }

  let res;
  try {
    res = await fetch(BASE + path, opts);
  } catch {
    throw new ApiError(0, 'NETWORK', 'Cannot reach the server. Check your connection and try again.');
  }

  if (res.status === 204) return null;

  let data = null;
  if ((res.headers.get('content-type') || '').includes('application/json')) {
    data = await res.json().catch(() => null);
  }

  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/auth/login')) {
      window.dispatchEvent(new Event('auth:unauthorized'));
    }
    throw new ApiError(
      res.status,
      data?.error?.code || `HTTP_${res.status}`,
      extractMessage(data, res.status),
      data?.error?.details
    );
  }
  return data;
}

const enc = encodeURIComponent;

export const api = {
  // Auth
  login: (email, password) => request('/auth/login', { method: 'POST', body: { email, password } }),
  logout: () => request('/auth/logout', { method: 'POST' }),
  me: () => request('/auth/me'),

  // Users (admin)
  listUsers: () => request('/users'),
  createUser: (body) => request('/users', { method: 'POST', body }),
  updateUser: (id, body) => request(`/users/${enc(id)}`, { method: 'PATCH', body }),

  // Assessments
  listAssessments: (status) => request('/assessments' + (status ? `?status=${enc(status)}` : '')),
  createAssessment: (body) => request('/assessments', { method: 'POST', body }),
  getAssessment: (id) => request(`/assessments/${enc(id)}`),
  updateAssessment: (id, body) => request(`/assessments/${enc(id)}`, { method: 'PATCH', body }),
  deleteAssessment: (id) => request(`/assessments/${enc(id)}`, { method: 'DELETE' }),
  closeAssessment: (id) => request(`/assessments/${enc(id)}/close`, { method: 'POST' }),
  uploadJd: (id, file) => {
    const fd = new FormData();
    fd.append('file', file);
    return request(`/assessments/${enc(id)}/jd-file`, { method: 'POST', formData: fd });
  },

  // AI jobs + questions
  generate: (id, body = {}) => request(`/assessments/${enc(id)}/generate`, { method: 'POST', body }),
  getJob: (jobId) => request(`/jobs/${enc(jobId)}`),
  listQuestions: (id) => request(`/assessments/${enc(id)}/questions`),
  addQuestion: (id, body) => request(`/assessments/${enc(id)}/questions`, { method: 'POST', body }),
  updateQuestion: (qid, body) => request(`/questions/${enc(qid)}`, { method: 'PATCH', body }),
  deleteQuestion: (qid) => request(`/questions/${enc(qid)}`, { method: 'DELETE' }),
  regenerateQuestion: (qid) => request(`/questions/${enc(qid)}/regenerate`, { method: 'POST' }),
  approve: (id) => request(`/assessments/${enc(id)}/approve`, { method: 'POST' }),

  // Participants
  listParticipants: (id) => request(`/assessments/${enc(id)}/participants`),
  addParticipants: (id, body) => request(`/assessments/${enc(id)}/participants`, { method: 'POST', body }),
  deleteParticipant: (pid) => request(`/participants/${enc(pid)}`, { method: 'DELETE' }),
  sendInvitations: (id, body = {}) => request(`/assessments/${enc(id)}/invitations`, { method: 'POST', body }),
  resend: (pid) => request(`/participants/${enc(pid)}/resend`, { method: 'POST' }),

  // Results
  results: (id, sort = 'score') => request(`/assessments/${enc(id)}/results?sort=${enc(sort)}`),
  getAttempt: (attemptId) => request(`/attempts/${enc(attemptId)}`),
  override: (attemptId, qid, body) =>
    request(`/attempts/${enc(attemptId)}/scores/${enc(qid)}/override`, { method: 'POST', body }),
};

// Poll a background job (AI work) every 2 s until done / failed / timeout.
export async function waitForJob(jobId, { timeoutMs = 180000 } = {}) {
  const start = Date.now();
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const job = await api.getJob(jobId);
    if (job.status === 'done') return job;
    if (job.status === 'failed') {
      throw new ApiError(422, 'JOB_FAILED', job.error || 'The AI job failed. Please try again.');
    }
    if (Date.now() - start > timeoutMs) {
      throw new ApiError(504, 'JOB_TIMEOUT', 'The AI job is taking too long. Please check again in a minute.');
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
}

// Download CSV / PDF export as a file (works with the cookie session).
export async function downloadExport(id, format) {
  let res;
  try {
    res = await fetch(`${BASE}/assessments/${enc(id)}/export?format=${format}`, { credentials: 'same-origin' });
  } catch {
    throw new ApiError(0, 'NETWORK', 'Cannot reach the server.');
  }
  if (!res.ok) {
    let data = null;
    try { data = await res.json(); } catch { /* not json */ }
    throw new ApiError(res.status, data?.error?.code || `HTTP_${res.status}`, extractMessage(data, res.status));
  }
  const blob = await res.blob();
  const cd = res.headers.get('content-disposition') || '';
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const filename = match ? decodeURIComponent(match[1]) : `results.${format}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
