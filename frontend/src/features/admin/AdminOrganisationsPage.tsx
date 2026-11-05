import { useMemo, useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ADMIN_ORGANISATIONS } from './adminData';

export function AdminOrganisationsPage() {
  const { t } = usePrefs();
  const [q, setQ] = useState('');

  const orgs = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return needle ? ADMIN_ORGANISATIONS.filter((o) => `${o.name} ${o.accountManager}`.toLowerCase().includes(needle)) : ADMIN_ORGANISATIONS;
  }, [q]);

  return (
    <>
      <div className="ad-head">
        <h2 className="ad-title">{t('Organisation directory')}</h2>
        <button type="button" className="ad-btn">{t('Add organisation')}</button>
      </div>
      <p className="ad-meta">{t('Assign client organisations to Account Managers.')}</p>

      <form className="ad-toolbar" role="search" onSubmit={(e) => e.preventDefault()}>
        <input className="ad-search" type="search" placeholder={t('Search organisations...')} aria-label={t('Search organisations')} value={q} onChange={(e) => setQ(e.target.value)} />
      </form>

      <div className="ad-table-wrap">
        <table className="ad-table ad-table--org">
          <colgroup><col style={{ width: 420 }} /><col style={{ width: 340 }} /><col style={{ width: 220 }} /><col /></colgroup>
          <thead>
            <tr>
              <th scope="col">{t('Organisation')}</th>
              <th scope="col">{t('Account Manager')}</th>
              <th scope="col">{t('Status')}</th>
              <th scope="col"><span className="ad-sr">{t('Actions')}</span></th>
            </tr>
          </thead>
          <tbody>
            {!orgs.length && (
              <tr><td className="ad-empty" colSpan={4}>{t('No organisations match your search.')}</td></tr>
            )}
            {orgs.map((o) => (
              <tr key={o.id}>
                <td>{o.name}</td>
                <td>{o.accountManager}</td>
                <td>{t(o.status)}</td>
                <td><a href={`#${o.id}`}>{t('Manage')}</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
