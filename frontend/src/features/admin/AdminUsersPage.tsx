import { useEffect, useState } from 'react';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import {
  ASSIGNABLE_ROLES,
  ROLE_LABEL,
  useAdminUsers,
  useCreateUser,
  useNewInvite,
  useSetUserActive,
  useUpdateUser,
  type AdminUser,
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
  const [dialog, setDialog] = useState<'new' | AdminUser | null>(null);
  const [invite, setInvite] = useState<CreatedUser | null>(null);

  const list = useAdminUsers(useDebounced(q), role, status);
  const users = list.data?.items ?? [];
  const filtered = !!(q || role || status !== 'all');

  return (
    <>
      <div className="ad-head">
        <h2 className="ad-title">{t('User directory')}</h2>
        <button type="button" className="ad-btn" onClick={() => setDialog('new')}>{t('Add employee')}</button>
      </div>
      <p className="ad-meta">
        {list.data ? t('{n} users · {a} active', { n: list.data.total, a: list.data.active_total }) : ' '}
      </p>

      <form className="ad-toolbar" role="search" onSubmit={(e) => e.preventDefault()}>
        <input className="ad-search" type="search" placeholder={t('Search users...')} aria-label={t('Search users')} value={q} onChange={(e) => setQ(e.target.value)} />
        <button type="button" className="ad-filter" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((o) => !o)}>
          <svg viewBox="0 0 14 14" fill="currentColor" aria-hidden="true"><rect x="1" y="2" width="2" height="2" /><rect x="5" y="2" width="8" height="2" /><rect x="1" y="6" width="2" height="2" /><rect x="5" y="6" width="8" height="2" /><rect x="1" y="10" width="2" height="2" /><rect x="5" y="10" width="8" height="2" /></svg>
          {t('Filter')}
        </button>
        {filtersOpen && (
          <>
            <select className="ad-select" aria-label={t('Role')} value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="">{t('All roles')}</option>
              {ASSIGNABLE_ROLES.map((r) => <option key={r} value={r}>{t(ROLE_LABEL[r])}</option>)}
            </select>
            <select className="ad-select" aria-label={t('Status')} value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)}>
              <option value="all">{t('All statuses')}</option>
              <option value="active">{t('Active')}</option>
              <option value="inactive">{t('Inactive')}</option>
            </select>
            {filtered && (
              <button type="button" className="ad-link" onClick={() => { setQ(''); setRole(''); setStatus('all'); }}>
                {t('Clear filters')}
              </button>
            )}
          </>
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
                <td><button type="button" className="ad-link" onClick={() => setDialog(u)}>{u.name}</button></td>
                <td>{u.email}</td>
                <td>{t(ROLE_LABEL[u.role] ?? u.role)}</td>
                <td>{u.projects.map((p) => p.name).join(', ') || '–'}</td>
                <td>
                  {t(u.is_active ? 'Active' : 'Inactive')}
                  {u.is_active && u.invite_pending && <span className="ad-tag">{t('Invited')}</span>}
                </td>
                <td><button type="button" className="ad-link" onClick={() => setDialog(u)}>{t('Manage')}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dialog && (
        <UserDialog
          user={dialog === 'new' ? null : dialog}
          onClose={() => setDialog(null)}
          onInvite={(c) => {
            setDialog(null);
            setInvite(c);
          }}
        />
      )}
      {invite && <InviteDialog created={invite} onClose={() => setInvite(null)} />}
    </>
  );
}

function UserDialog({ user, onClose, onInvite }: { user: AdminUser | null; onClose: () => void; onInvite: (c: CreatedUser) => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const create = useCreateUser();
  const update = useUpdateUser();
  const setActive = useSetUserActive();
  const newInvite = useNewInvite();

  const [name, setName] = useState(user?.name ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [role, setRole] = useState<string>(user?.role ?? 'developer');
  const [joinDate, setJoinDate] = useState(user?.join_date ?? '');
  const [tried, setTried] = useState(false);
  const [error, setError] = useState('');

  const errors = {
    name: name.trim() ? '' : 'Enter a name.',
    email: EMAIL_RE.test(email.trim()) ? '' : 'Enter a valid email address.',
  };
  const busy = create.isPending || update.isPending || setActive.isPending || newInvite.isPending;
  // Roles outside the assignable set (e.g. client) are shown but cannot be changed here.
  const roleLocked = !!user && !ASSIGNABLE_ROLES.includes(user.role as AssignableRole);

  const fail = (e: unknown) => setError(describeApiError(e, t('That didn’t work. Try again.')));

  const save = async () => {
    setTried(true);
    setError('');
    if (errors.name || errors.email) return;
    const body = { name: name.trim(), email: email.trim(), role: role as AssignableRole, join_date: joinDate || null };
    try {
      if (!user) {
        onInvite(await create.mutateAsync(body));
      } else {
        await update.mutateAsync({ id: user.id, name: body.name, email: body.email, join_date: body.join_date, ...(roleLocked ? {} : { role: body.role }) });
        toast.success('User updated.');
        onClose();
      }
    } catch (e) {
      fail(e);
    }
  };

  const toggle = async () => {
    if (!user) return;
    setError('');
    try {
      await setActive.mutateAsync({ id: user.id, active: !user.is_active });
      toast.success(user.is_active ? 'User deactivated.' : 'User activated.');
      onClose();
    } catch (e) {
      fail(e);
    }
  };

  const resend = async () => {
    if (!user) return;
    setError('');
    try {
      onInvite(await newInvite.mutateAsync(user.id));
    } catch (e) {
      fail(e);
    }
  };

  return (
    <Dialog title={user ? 'Manage user' : 'Add employee'} onClose={onClose} onSubmit={save}>
      <Field label="Name" error={tried ? errors.name : ''}>
        <input className="ad-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="off" />
      </Field>
      <Field label="Email" error={tried ? errors.email : ''}>
        <input className="ad-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={320} autoComplete="off" />
      </Field>
      <Field label="Role">
        <select className="ad-input" value={role} onChange={(e) => setRole(e.target.value)} disabled={roleLocked}>
          {roleLocked && <option value={role}>{t(ROLE_LABEL[role] ?? role)}</option>}
          {ASSIGNABLE_ROLES.map((r) => <option key={r} value={r}>{t(ROLE_LABEL[r])}</option>)}
        </select>
      </Field>
      <Field label="Joining date">
        <input className="ad-input" type="date" value={joinDate} onChange={(e) => setJoinDate(e.target.value)} />
      </Field>
      <Field label="Account status">
        <input className="ad-input" readOnly value={t(!user ? 'Pending activation' : user.is_active ? 'Active' : 'Inactive')} />
      </Field>
      {!user && <p className="ad-hint">{t('We’ll create the account and give you a one-time sign-in link to share.')}</p>}
      {error && <p className="ad-error" role="alert">{error}</p>}
      <div className="ad-actions">
        {user && (
          <div className="ad-actions-left">
            <button type="button" className="ad-btn ad-btn--ghost" disabled={busy} onClick={resend}>{t('New sign-in link')}</button>
            <button type="button" className="ad-btn ad-btn--ghost ad-btn--danger" disabled={busy} onClick={toggle}>
              {t(user.is_active ? 'Deactivate' : 'Activate')}
            </button>
          </div>
        )}
        <button type="button" className="ad-btn ad-btn--ghost" onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="ad-btn" disabled={busy}>{t(user ? 'Save changes' : 'Create account')}</button>
      </div>
    </Dialog>
  );
}

function InviteDialog({ created, onClose }: { created: CreatedUser; onClose: () => void }) {
  const { t, lang } = usePrefs();
  const [copied, setCopied] = useState(false);
  const expires = new Date(created.invite.expires_at).toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(created.invite.url);
      setCopied(true);
    } catch {
      /* clipboard blocked: the link stays selectable in the field */
    }
  };

  return (
    <Dialog title="Sign-in link" onClose={onClose}>
      <p className="ad-hint">
        {t('Share this link with {name}. It works once and expires on {date}. It won’t be shown again.', { name: created.user.name, date: expires })}
      </p>
      <input className="ad-input" readOnly value={created.invite.url} aria-label={t('Sign-in link')} onFocus={(e) => e.currentTarget.select()} />
      <div className="ad-actions">
        <button type="button" className="ad-btn ad-btn--ghost" onClick={copy}>{t(copied ? 'Copied' : 'Copy link')}</button>
        <button type="button" className="ad-btn" onClick={onClose}>{t('Done')}</button>
      </div>
    </Dialog>
  );
}
