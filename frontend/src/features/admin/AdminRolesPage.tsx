import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ADMIN_ROLES } from './adminData';

export function AdminRolesPage() {
  const { t } = usePrefs();

  return (
    <>
      <h2 className="ad-title">{t('Roles')}</h2>
      <p className="ad-sub">{t('Choose a role to manage its navigation and actions.')}</p>
      <ul className="ad-roles">
        {ADMIN_ROLES.map((r) => (
          <li className="ad-role" key={r.id}>
            <span className="ad-role-name">{t(r.name)}</span>
            <span className="ad-role-count">{t(r.users === 1 ? '{n} user' : '{n} users', { n: r.users })}</span>
            <a className="ad-role-manage" href={`#${r.id}`} aria-label={t('Manage {role}', { role: t(r.name) })}>
              {t('Manage')}
              <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2 7h10M8 3l4 4-4 4" /></svg>
            </a>
          </li>
        ))}
      </ul>
    </>
  );
}
