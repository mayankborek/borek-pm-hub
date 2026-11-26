import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useAdminUsers } from './adminApi';
import { useOrganisations } from './organisationsApi';
import { UsersTabs } from './AdminUsersPage';

export function AdminOrganisationsPage() {
  const { t } = usePrefs();
  const list = useOrganisations();
  const contacts = useAdminUsers('', 'client', 'all');
  const orgs = (list.data?.items ?? []).filter((o) => !o.archived_at);

  // Projects and contacts of an organisation come from its client contacts.
  const byOrg = useMemo(() => {
    const map = new Map<string, { projects: string[]; people: string[] }>();
    for (const u of contacts.data?.items ?? []) {
      if (!u.organisation || !u.is_active) continue;
      const entry = map.get(u.organisation.id) ?? { projects: [], people: [] };
      entry.people.push(u.name);
      for (const p of u.projects) if (!entry.projects.includes(p.name)) entry.projects.push(p.name);
      map.set(u.organisation.id, entry);
    }
    return map;
  }, [contacts.data]);

  return (
    <main className="bf-content">
      <div className="bf-head">
        <h1>{t('Client organisations')}</h1>
        <Link className="bf-btn primary" to={paths.adminOrganisationNew}>{t('New client organisation')}</Link>
      </div>
      <UsersTabs active="organisations" />
      <section className="bf-card">
        <div className="bf-card-head" style={{ height: 49 }}><h3>{t('Organisations')}</h3></div>
        {list.isError && (
          <p className="bf-error" role="alert" style={{ padding: '0 18px 12px' }}>
            {describeApiError(list.error, t('We couldn’t load organisations'))}{' '}
            <button type="button" className="bf-link" onClick={() => list.refetch()}>{t('Retry')}</button>
          </p>
        )}
        <table className="bf-orgs" aria-busy={list.isFetching}>
          <thead>
            <tr>
              <th style={{ width: '29%' }}>{t('Organisation')}</th>
              <th style={{ width: '27%' }}>{t('Project')}</th>
              <th>{t('Client contacts')}</th>
              <th className="r">{t('Actions')}</th>
            </tr>
          </thead>
          <tbody>
            {list.isPending && <tr><td className="bf-empty" colSpan={4}>{t('Loading organisations')}</td></tr>}
            {list.data && !orgs.length && <tr><td className="bf-empty" colSpan={4}>{t('No organisations yet.')}</td></tr>}
            {orgs.map((o) => {
              const info = byOrg.get(o.id);
              return (
                <tr key={o.id}>
                  <td><b>{o.name}</b></td>
                  <td>{info?.projects.join(', ') || '–'}</td>
                  <td>{info?.people.join(', ') || '–'}</td>
                  <td className="r"><Link className="bf-btn" to={paths.adminOrganisation(o.id)}>{t('Manage')}</Link></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </main>
  );
}
