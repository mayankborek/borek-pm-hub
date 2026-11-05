import { useMemo, useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ADMIN_USERS } from './adminData';

export function AdminUsersPage() {
  const { t } = usePrefs();
  const [q, setQ] = useState('');

  const users = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return needle ? ADMIN_USERS.filter((u) => `${u.name} ${u.email}`.toLowerCase().includes(needle)) : ADMIN_USERS;
  }, [q]);
  const active = ADMIN_USERS.filter((u) => u.status === 'Active').length;

  return (
    <>
      <div className="ad-head">
        <h2 className="ad-title">{t('User directory')}</h2>
        <button type="button" className="ad-btn">{t('Add employee')}</button>
      </div>
      <p className="ad-meta">{t('{n} users · {a} active', { n: ADMIN_USERS.length, a: active })}</p>

      <form className="ad-toolbar" role="search" onSubmit={(e) => e.preventDefault()}>
        <input className="ad-search" type="search" placeholder={t('Search users...')} aria-label={t('Search users')} value={q} onChange={(e) => setQ(e.target.value)} />
        <button type="button" className="ad-filter">
          <svg viewBox="0 0 14 14" fill="currentColor" aria-hidden="true"><rect x="1" y="2" width="2" height="2" /><rect x="5" y="2" width="8" height="2" /><rect x="1" y="6" width="2" height="2" /><rect x="5" y="6" width="8" height="2" /><rect x="1" y="10" width="2" height="2" /><rect x="5" y="10" width="8" height="2" /></svg>
          {t('Filter')}
        </button>
      </form>

      <div className="ad-table-wrap">
        <table className="ad-table">
          <colgroup><col style={{ width: 180 }} /><col style={{ width: 300 }} /><col style={{ width: 180 }} /><col style={{ width: 340 }} /><col /></colgroup>
          <thead>
            <tr>
              <th scope="col">{t('Name')}</th>
              <th scope="col">{t('Email')}</th>
              <th scope="col">{t('Role')}</th>
              <th scope="col">{t('Project')}</th>
              <th scope="col">{t('Status')}</th>
            </tr>
          </thead>
          <tbody>
            {!users.length && (
              <tr><td className="ad-empty" colSpan={5}>{t('No users match your search.')}</td></tr>
            )}
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.linked ? <a href={`#${u.id}`}>{u.name}</a> : u.name}</td>
                <td>{u.email}</td>
                <td>{t(u.role)}</td>
                <td>{u.projects.join(', ')}</td>
                <td>{t(u.status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
