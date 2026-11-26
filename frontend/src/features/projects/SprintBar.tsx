import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/features/auth/AuthContext';
import { api, describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { formatDate } from './projectUi';
import './sprintBar.css';

/** Mirrors the fields of backend SprintOut that the bar shows. */
interface Sprint {
  id: string;
  name: string;
  state: 'planned' | 'active' | 'completed';
  start_date: string | null;
  end_date: string | null;
  version: number;
}

const sprintKey = (projectId: string) => ['projects', 'sprints', projectId] as const;

/** Board header (Figma "Board"): the active sprint, its dates and Complete sprint. Unfinished tasks go back to the backlog. */
export function SprintBar({ projectId }: { projectId: string }) {
  const { t } = usePrefs();
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const sprints = useQuery({ queryKey: sprintKey(projectId), queryFn: () => api<{ items: Sprint[] }>(`/projects/${projectId}/sprints`), retry: false });
  const complete = useMutation({
    mutationFn: (s: Sprint) => api(`/projects/${projectId}/sprints/${s.id}/complete`, { method: 'POST', body: JSON.stringify({ version: s.version }) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: sprintKey(projectId) });
      void qc.invalidateQueries({ queryKey: ['projects', projectId] });
      void qc.invalidateQueries({ queryKey: ['tasks'] });
    },
    onError: (e) => toast.error(describeApiError(e, t('Could not complete the sprint.'))),
  });

  const items = sprints.data?.items ?? [];
  const active = items.find((s) => s.state === 'active');
  // No active sprint: show the next planned one, or an empty bar, so the board header keeps its place.
  const shown = active ?? items.find((s) => s.state === 'planned');

  const confirmComplete = () => {
    if (active && window.confirm(t('Complete {name}? Unfinished tasks move back to the backlog.', { name: active.name }))) complete.mutate(active);
  };

  return (
    <div className="sprint-bar">
      <b>{shown?.name ?? t('No active sprint')}</b>
      {shown && <span className="sprint-chev" aria-hidden="true">⌄</span>}
      {shown && <span className="sprint-chip">{t(shown.state === 'active' ? 'Active' : 'Planned')}</span>}
      {shown?.start_date && <span>{formatDate(shown.start_date)}</span>}
      {shown?.end_date && <span>– {formatDate(shown.end_date)}</span>}
      <span className="sprint-gap" />
      <span className="sprint-menu" aria-hidden="true">≡</span>
      {active && user?.role === 'pm' && (
        <button type="button" className="btn" disabled={complete.isPending} onClick={confirmComplete}>
          {t('Complete sprint')}
        </button>
      )}
    </div>
  );
}
