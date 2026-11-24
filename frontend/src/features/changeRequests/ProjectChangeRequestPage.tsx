import { Link, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Pill } from '@/shared/ui/Pill';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useProjectContext } from '@/features/projects/ProjectLayout';
import { useStaffChangeRequests } from './changeRequestsStaffApi';
import { RequestDetail, STATUS } from './ProjectChangeRequestsPage';
import '@/features/requirements/requirements.css';
import './changeRequests.css';

/** One change request on its own page: details, proposed impact, decision and the shared conversation. */
export function ProjectChangeRequestPage() {
  const { requestId } = useParams();
  const project = useProjectContext();
  const { t } = usePrefs();
  const list = useStaffChangeRequests(project.id);

  if (list.isError) return <ErrorState title="We couldn’t load the change request" onRetry={() => void list.refetch()} />;
  if (!list.data) return <LoadingState title="Loading change request" />;
  const cr = list.data.items.find((r) => r.id === requestId);
  if (!cr) return <ErrorState title="Change request not found" text="It may have been removed." />;
  const s = STATUS[cr.status];

  return (
    <section className="crq-review" aria-label={t('Change Request review')}>
      <Link className="crq-back" to={paths.projectChangeRequests(project.id)}>← {t('All requests')}</Link>
      <h2>{cr.title}</h2>
      <div className="crq-flag">{cr.code} · <Pill tone={s.tone}>{s.label}</Pill></div>
      <div className="req-card"><RequestDetail cr={cr} projectId={project.id} /></div>
    </section>
  );
}
