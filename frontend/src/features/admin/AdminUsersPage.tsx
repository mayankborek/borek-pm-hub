import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import {
  ASSIGNABLE_ROLES,
  ROLE_LABEL,
  useAdminUsers,
  useCreateUser,
  type AssignableRole,
  type CreatedUser,
  type StatusFilter,
} from './adminApi';
import { Dialog, EMAIL_RE, Field } from './Dialog';

/** Waits for typing to pause so each keystroke is not a request. */
function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function AdminUsersPage() {
  const { t } = usePrefs();
  const [q, setQ] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState<StatusFilter>('all');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const navigate = useNavigate();
  const [adding, setAdding] = useState(false);

  const list = useAdminUsers(useDebounced(q), role, status);
  const users = list.data?.items ?? [];
  const filtered = !!(q || role || status !== 'all');
  const activeFilters = (role ? 1 : 0) + (status !== 'all' ? 1 : 0);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!filtersOpen) return;
    const away = (e: MouseEvent) => !menuRef.current?.contains(e.target as Node) && setFiltersOpen(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setFiltersOpen(false);
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', away);
      document.removeEventListener('keydown', esc);
    };
  }, [filtersOpen]);

  return (
    <>
      <div className="ad-head">
        <h2 className="ad-title">{t('User directory')}</h2>
        <button type="button" className="ad-btn" onClick={() => setAdding(true)}>{t('Add employee')}</button>
      </div>
      <p className="ad-meta">
        {list.data ? t('{n} users · {a} active', { n: list.data.total, a: list.data.active_total }) : ' '}
      </p>

      <form className="ad-toolbar" role="search" onSubmit={(e) => e.preventDefault()}>
        <input className="ad-search" type="search" placeholder={t('Search users...')} aria-label={t('Search users')} value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="ad-filter-menu" ref={menuRef}>
          <button type="button" className="ad-filter" aria-haspopup="dialog" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((o) => !o)}>
            <svg viewBox="0 0 14 14" fill="currentColor" aria-hidden="true"><rect x="1" y="2" width="2" height="2" /><rect x="5" y="2" width="8" height="2" /><rect x="1" y="6" width="2" height="2" /><rect x="5" y="6" width="8" height="2" /><rect x="1" y="10" width="2" height="2" /><rect x="5" y="10" width="8" height="2" /></svg>
            {t('Filter')}
            {activeFilters > 0 && <span className="ad-filter-count">{activeFilters}</span>}
            <span aria-hidden="true">▾</span>
          </button>
          {filtersOpen && (
            <div className="ad-filter-panel" role="dialog" aria-label={t('Filters')}>
              <div className="ad-filter-head">
                <strong>{t('Filters')}</strong>
                {activeFilters > 0 && (
                  <button type="button" className="ad-link" onClick={() => { setRole(''); setStatus('all'); }}>{t('Clear all')}</button>
                )}
                <button type="button" className="ad-filter-close" aria-label={t('Close')} onClick={() => setFiltersOpen(false)}>✕</button>
              </div>
              <div className="ad-filter-group" role="group" aria-label={t('Role')}>
                <h4>{t('Role')}</h4>
                {ASSIGNABLE_ROLES.map((r) => (
                  <label key={r} className="ad-filter-opt">
                    <input type="checkbox" checked={role === r} onChange={() => setRole(role === r ? '' : r)} />
                    {t(ROLE_LABEL[r])}
                  </label>
                ))}
              </div>
              <div className="ad-filter-group" role="group" aria-label={t('Status')}>
                <h4>{t('Status')}</h4>
                {(['active', 'inactive'] as const).map((s) => (
                  <label key={s} className="ad-filter-opt">
                    <input type="checkbox" checked={status === s} onChange={() => setStatus(status === s ? 'all' : s)} />
                    {t(s === 'active' ? 'Active' : 'Inactive')}
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
        {filtered && (
          <button type="button" className="ad-link" onClick={() => { setQ(''); setRole(''); setStatus('all'); }}>
            {t('Clear filters')}
          </button>
        )}
      </form>

      {list.isError && (
        <p className="ad-error" role="alert">
          {describeApiError(list.error, t('We couldn’t load users'))}{' '}
          <button type="button" className="ad-link" onClick={() => list.refetch()}>{t('Retry')}</button>
        </p>
      )}

      <div className="ad-table-wrap">
        <table className="ad-table" aria-busy={list.isFetching}>
          <colgroup><col style={{ width: 180 }} /><col style={{ width: 280 }} /><col style={{ width: 160 }} /><col style={{ width: 280 }} /><col style={{ width: 120 }} /><col /></colgroup>
          <thead>
            <tr>
              <th scope="col">{t('Name')}</th>
              <th scope="col">{t('Email')}</th>
              <th scope="col">{t('Role')}</th>
              <th scope="col">{t('Project')}</th>
              <th scope="col">{t('Status')}</th>
              <th scope="col"><span className="ad-sr">{t('Actions')}</span></th>
            </tr>
          </thead>
          <tbody>
            {list.isPending && <tr><td className="ad-empty" colSpan={6}>{t('Loading users')}</td></tr>}
            {list.data && !users.length && <tr><td className="ad-empty" colSpan={6}>{t('No users match your search.')}</td></tr>}
            {users.map((u) => (
              <tr key={u.id} className={u.is_active ? undefined : 'ad-off'}>
                <td><Link to={paths.adminUser(u.id)}>{u.name}</Link></td>
                <td>{u.email}</td>
                <td>{t(ROLE_LABEL[u.role] ?? u.role)}</td>
                <td>{u.projects.map((p) => p.name).join(', ') || '–'}</td>
                <td>
                  {t(u.is_active ? 'Active' : 'Inactive')}
                  {u.is_active && u.invite_pending && <span className="ad-tag">{t('Invited')}</span>}
                </td>
                <td><Link to={paths.adminUser(u.id)}>{t('Manage')}</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {adding && (
        <AddEmployeeDialog
          onClose={() => setAdding(false)}
          onCreated={(created) => navigate(paths.adminUserInvitation(created.user.id), { state: { created } })}
        />
      )}
    </>
  );
}

function AddEmployeeDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (c: CreatedUser) => void }) {
  const { t } = usePrefs();
  const create = useCreateUser();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<string>('developer');
  const [joinDate, setJoinDate] = useState('');
  const [tried, setTried] = useState(false);
  const [error, setError] = useState('');

  const errors = {
    name: name.trim() ? '' : 'Enter a name.',
    email: EMAIL_RE.test(email.trim()) ? '' : 'Enter a valid email address.',
  };

  const save = async () => {
    setTried(true);
    setError('');
    if (errors.name || errors.email) return;
    try {
      onCreated(await create.mutateAsync({ name: name.trim(), email: email.trim(), role: role as AssignableRole, join_date: joinDate || null }));
    } catch (e) {
      setError(describeApiError(e, t('That didn’t work. Try again.')));
    }
  };

  return (
    <Dialog title="Add employee" onClose={onClose} onSubmit={save}>
      <Field label="Full name" error={tried ? errors.name : ''}>
        <input className="ad-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="off" />
      </Field>
      <Field label="Work email" error={tried ? errors.email : ''}>
        <input className="ad-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={320} autoComplete="off" />
      </Field>
      <Field label="Joining date">
        <input className="ad-input" type="date" value={joinDate} onChange={(e) => setJoinDate(e.target.value)} />
      </Field>
      <Field label="Role">
        <select className="ad-input" value={role} onChange={(e) => setRole(e.target.value)}>
          {ASSIGNABLE_ROLES.map((r) => <option key={r} value={r}>{t(ROLE_LABEL[r])}</option>)}
        </select>
      </Field>
      <Field label="Account status">
        <input className="ad-input" readOnly value={t('Pending activation')} />
      </Field>
      <p className="ad-hint">{t('We’ll create the account and give you a one-time sign-in link to share.')}</p>
      {error && <p className="ad-error" role="alert">{error}</p>}
      <div className="ad-actions">
        <button type="button" className="ad-btn ad-btn--ghost" onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="ad-btn" disabled={create.isPending}>{t('Create account')}</button>
      </div>
    </Dialog>
  );
}
