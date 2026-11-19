import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { Dialog, Field } from './Dialog';
import { useAdminUsers } from './adminApi';
import { useCreateOrganisation, useOrganisations, useUpdateOrganisation, type Organisation } from './organisationsApi';

export function AdminOrganisationsPage() {
  const { t } = usePrefs();
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [adding, setAdding] = useState(false);
  const list = useOrganisations(q);
  const orgs = list.data?.items ?? [];

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

      {list.isError && (
        <p className="ad-error" role="alert">
          {describeApiError(list.error, t('We couldn’t load organisations'))}{' '}
          <button type="button" className="ad-link" onClick={() => list.refetch()}>{t('Retry')}</button>
        </p>
      )}

      <div className="ad-table-wrap">
        <table className="ad-table ad-table--org" aria-busy={list.isFetching}>
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
            {list.isPending && <tr><td className="ad-empty" colSpan={4}>{t('Loading organisations')}</td></tr>}
            {list.data && !orgs.length && <tr><td className="ad-empty" colSpan={4}>{t('No organisations match your search.')}</td></tr>}
            {orgs.map((o) => (
              <tr key={o.id} className={o.archived_at ? 'ad-off' : undefined}>
                <td><Link to={paths.adminOrganisation(o.id)}>{o.name}</Link></td>
                <td>{o.account_managers.map((m) => m.name).join(', ') || '–'}</td>
                <td>{t(o.archived_at ? 'Inactive' : 'Active')}</td>
                <td><Link to={paths.adminOrganisation(o.id)}>{t('Manage')}</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {adding && <OrganisationDialog onClose={() => setAdding(false)} onSaved={(org) => navigate(paths.adminOrganisation(org.id))} />}
    </>
  );
}

/** Create (no `org`) or edit an organisation's name and Account Manager. */
export function OrganisationDialog({
  org,
  onClose,
  onSaved,
}: {
  org?: Organisation;
  onClose: () => void;
  onSaved?: (org: Organisation) => void;
}) {
  const { t } = usePrefs();
  const toast = useToast();
  const create = useCreateOrganisation();
  const update = useUpdateOrganisation();
  const [name, setName] = useState(org?.name ?? '');
  const [managerId, setManagerId] = useState(org?.account_managers[0]?.id ?? '');
  const [tried, setTried] = useState(false);
  const [error, setError] = useState('');
  const managers = useAdminUsers('', 'account_manager', 'active').data?.items ?? [];

  const nameError = name.trim() ? '' : 'Enter an organisation name.';

  const save = async () => {
    setTried(true);
    setError('');
    if (nameError) return;
    try {
      if (org) {
        await update.mutateAsync({ org, name: name.trim(), managerId });
        toast.success('Organisation updated.');
        onSaved?.(org);
      } else {
        const created = await create.mutateAsync({ name: name.trim(), managerId });
        toast.success('Organisation added.');
        onSaved?.(created);
      }
      onClose();
    } catch (e) {
      setError(describeApiError(e, t('That didn’t work. Try again.')));
    }
  };

  return (
    <Dialog title={org ? 'Edit organisation' : 'Add organisation'} onClose={onClose} onSubmit={save}>
      <Field label="Organisation" error={tried ? nameError : ''}>
        <input className="ad-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="off" />
      </Field>
      <Field label="Account Manager">
        <select className="ad-input" value={managerId} onChange={(e) => setManagerId(e.target.value)}>
          <option value="">{t('Select Account Manager')}</option>
          {managers.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select>
      </Field>
      {error && <p className="ad-error" role="alert">{error}</p>}
      <div className="ad-actions">
        <button type="button" className="ad-btn ad-btn--ghost" onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="ad-btn" disabled={create.isPending || update.isPending}>{t(org ? 'Save changes' : 'Add organisation')}</button>
      </div>
    </Dialog>
  );
}
