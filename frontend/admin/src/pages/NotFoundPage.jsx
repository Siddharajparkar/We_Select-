import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="state">
      <h2>Page not found</h2>
      <p className="muted">The page you are looking for does not exist.</p>
      <Link className="btn btn-primary" to="/assessments">Go to assessments</Link>
    </div>
  );
}