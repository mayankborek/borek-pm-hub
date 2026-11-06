import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { orgActions, useOrganisations, type AdminOrganisation } from './adminStore';
import { Dialog, Field } from './Dialog';
import { useAdminUsers } from './adminApi';

export function AdminOrganisationsPage() {
  const { t } = usePrefs();
  const navigate = useNavigate();
  const all = useOrganisations();
  const [q, setQ] = useState('');
  const [adding, setAdding] = useState(false);

  const orgs = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return needle ? all.filter((o) => `${o.name} ${o.accountManager}`.toLowerCase().includes(needle)) : all;
  }, [q, all]);

  return (
    <>
      <div className="ad-head">
        <h2 className="ad-title">{t('Organisation directory')}</h2>
        <button type="button" className="ad-btn" onClick={() => setAdding(true)}>{t('Add organisation')}</button>
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
            {!orgs.length && <tr><td className="ad-empty" colSpan={4}>{t('No organisations match your search.')}</td></tr>}
            {orgs.map((o) => (
              <tr key={o.id} className={o.active ? undefined : 'ad-off'}>
                <td><Link to={paths.adminOrganisation(o.id)}>{o.name}</Link></td>
                <td>{o.accountManager || '–'}</td>
                <td>{t(o.active ? 'Active' : 'Inactive')}</td>
                <td><Link to={paths.adminOrganisation(o.id)}>{t('Manage')}</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {adding && (
        <OrganisationDialog
          onClose={() => setAdding(false)}
          onSave={(name, manager) => navigate(paths.adminOrganisation(orgActions.add(name, manager)))}
        />
      )}
    </>
  );
}

/** Create (no `org`) or edit an organisation's name, Account Manager and status. */
export function OrganisationDialog({
  org,
  onClose,
  onSave,
}: {
  org?: AdminOrganisation;
  onClose: () => void;
  onSave: (name: string, accountManager: string, active: boolean) => void;
}) {
  const { t } = usePrefs();
  const toast = useToast();
  const [name, setName] = useState(org?.name ?? '');
  const [manager, setManager] = useState(org?.accountManager ?? '');
  const [active, setActive] = useState(org?.active ?? true);
  const [tried, setTried] = useState(false);
  const managers = useAdminUsers('', 'account_manager', 'active').data?.items ?? [];
  const others = useOrganisations().filter((o) => o.id !== org?.id);

  const error = !name.trim() ? 'Enter an organisation name.' : others.some((o) => o.name.toLowerCase() === name.trim().toLowerCase()) ? 'An organisation with this name already exists.' : '';

  const save = () => {
    setTried(true);
    if (error) return;
    onSave(name.trim(), manager.trim(), active);
    toast.success(org ? 'Organisation updated.' : 'Organisation added.');
    onClose();
  };

  return (
    <Dialog title={org ? 'Edit organisation' : 'Add organisation'} onClose={onClose} onSubmit={save}>
      <Field label="Organisation" error={tried ? error : ''}>
        <input className="ad-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="off" />
      </Field>
      <Field label="Account Manager">
        <input className="ad-input" list="ad-managers" placeholder={t('Select Account Manager')} value={manager} onChange={(e) => setManager(e.target.value)} maxLength={200} autoComplete="off" />
        <datalist id="ad-managers">{managers.map((m) => <option key={m.id} value={m.name} />)}</datalist>
      </Field>
      {org && (
        <label className="ad-check">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          {t('Active')}
        </label>
      )}
      <div className="ad-actions">
        <button type="button" className="ad-btn ad-btn--ghost" onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="ad-btn">{t(org ? 'Save changes' : 'Add organisation')}</button>
      </div>
    </Dialog>
  );
}
