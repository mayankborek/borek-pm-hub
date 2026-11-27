import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ErrorState, LoadingState } from '@/shared/ui/States';
import { useProjectContext } from '@/features/projects/ProjectLayout';
import { AcceptanceFlow } from './AcceptanceFlow';
import { RequirementForm } from './ProjectRequirementsPage';
import { useRequirements } from './requirementsApi';
import './requirements.css';
import './requirementDetail.css';

/** Requirement details (requirement-details.html): owner, version, summary and acceptance criteria, under the Change Requests tab. */
export function RequirementDetailPage() {
  const project = useProjectContext();
  const { requirementId } = useParams();
  const { t } = usePrefs();
  const list = useRequirements(project.id);
  const [editing, setEditing] = useState(false);

  if (list.isError) return <ErrorState title="We couldn’t load the requirement" onRetry={() => void list.refetch()} />;
  if (!list.data) return <LoadingState title="Loading requirement" />;
  const r = list.data.items.find((x) => x.id === requirementId);
  if (!r) return <ErrorState title="Requirement not found" text="It may have been removed." />;

  const shown = r.versions.find((v) => v.number === (r.published_version ?? r.current_version)) ?? r.versions[0];
  const closed = r.status === 'accepted' || r.status === 'rejected';

  return (
    <div className="rqd">
      <article className="rqd-card">
        <h2>{t('Requirement details')}</h2>
        <p className="rqd-owner">{t('Owner')}: {r.owner?.name ?? '—'}</p>
        <h2 className="rqd-req">{r.code} · {r.title}</h2>
        <p className="rqd-version">{t('Version')} {shown?.number ?? r.current_version}.0</p>
        <p className="rqd-summary">{shown?.description}</p>
        {!!shown?.acceptance_criteria.length && (
          <>
            <h3>{t('Acceptance criteria')}</h3>
            <ol>
              {shown.acceptance_criteria.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ol>
          </>
        )}
      </article>
      {editing ? (
        <RequirementForm projectId={project.id} requirement={r} onDone={() => setEditing(false)} />
      ) : (
        <div className="rqd-actions">
          {!closed && (
            <button type="button" className="rqd-btn primary" onClick={() => setEditing(true)}>
              {t('Edit requirement')}
            </button>
          )}
          <Link className="rqd-btn secondary" to={paths.projectChangeRequests(project.id)}>
            {t('Back to requirements')}
          </Link>
        </div>
      )}
      {!editing && <AcceptanceFlow requirement={r} projectId={project.id} onCorrect={() => setEditing(true)} />}
    </div>
  );
}
