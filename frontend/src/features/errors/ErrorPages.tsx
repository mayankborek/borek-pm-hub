import { Link } from 'react-router-dom';
import { useAuth } from '@/features/auth/AuthContext';
import { homeFor, paths } from '@/app/routes';

function ErrorPage({ title, text }: { title: string; text: string }) {
  const { user } = useAuth();
  return (
    <section className="page-body">
      <h1 className="page-title">{title}</h1>
      <p className="page-desc">{text}</p>
      <Link to={user ? homeFor(user.role) : paths.login}>Back to home</Link>
    </section>
  );
}

export const NotFoundPage = () => (
  <ErrorPage title="Page not found" text="The page you are looking for does not exist." />
);

export const ForbiddenPage = () => (
  <ErrorPage title="No permission" text="You do not have access to this page." />
);
