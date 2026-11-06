import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useAdminUsers } from './adminApi';
import { ROLES } from './adminStore';

export function AdminRolesPage() {
  const { t } = usePrefs();
  const users = useAdminUsers('', '', 'all');
  const count = (key: string) => (users.data?.items ?? []).filter((u) => u.role === key).length;

  return (
    <>
      <h2 className="ad-title">{t('Roles')}</h2>
      <p className="ad-sub">{t('Choose a role to manage its navigation and actions.')}</p>
      <ul className="ad-roles">
        {ROLES.map((r) => {
          const n = count(r.key);
          return (
            <li className="ad-role" key={r.id}>
              <Link className="ad-role-name" to={paths.adminRole(r.id)}>{t(r.name)}</Link>
              <span className="ad-role-count">{users.data ? t(n === 1 ? '{n} user' : '{n} users', { n }) : '–'}</span>
              <Link className="ad-role-manage" to={paths.adminRole(r.id)} aria-label={t('Manage {role}', { role: t(r.name) })}>
                {t('Manage')}
                <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2 7h10M8 3l4 4-4 4" /></svg>
              </Link>
            </li>
          );
        })}
      </ul>
    </>
  );
}
