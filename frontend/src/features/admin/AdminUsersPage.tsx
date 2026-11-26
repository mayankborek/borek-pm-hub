import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
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
import { useOrganisations } from './organisationsApi';
import { ConfirmModal, EMAIL_RE, Field, Modal, ShareLinkModal, Tabs, initials, usePopover } from './AdminUi';

/** Segmented role filter: label, backend role ('' = everyone). */
const ROLE_SEG: [string, string][] = [
  ['All users', ''],
  ['Developer', 'developer'],
  ['Project Manager', 'pm'],
  ['Account Manager', 'account_manager'],
  ['Manager', 'manager'],
  ['Administrator', 'admin'],
  ['Client contact', 'client'],
];

const STATUS_OPTIONS: [StatusFilter, string][] = [
  ['active', 'Active'],
  ['inactive', 'Deactivated'],
  ['all', 'Everyone'],
];

const today = () => new Date().toISOString().slice(0, 10);

export const organisationOf = (u: AdminUser) => u.organisation?.name ?? (u.role === 'client' ? 'Client organisation' : 'Borek Solutions');

export function UsersTabs({ active }: { active: 'employees' | 'organisations' }) {
  return (
    <Tabs
      items={[
        { to: paths.adminUsers, label: 'Employees', on: active === 'employees' },
        { to: paths.adminOrganisations, label: 'Client organisations', on: active === 'organisations' },
      ]}
    />
  );
}

export function AdminUsersPage() {
  const { t } = usePrefs();
  const navigate = useNavigate();
  const { userId } = useParams();
  const [q, setQ] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState<StatusFilter>('active');
  const [adding, setAdding] = useState<'employee' | 'invite' | null>(null);
  const [link, setLink] = useState<CreatedUser | null>(null);
  const statusMenu = usePopover();

  const list = useAdminUsers('', role, status);
  const all = list.data?.items ?? [];
  const users = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return all;
    return all.filter((u) => [u.name, u.email, organisationOf(u)].some((v) => v.toLowerCase().includes(needle)));
  }, [all, q]);
  const selected = userId ? all.find((u) => u.id === userId) : undefined;

  return (
    <main className="bf-content">
      <div className="bf-head">
        <h1>{t('Users')}</h1>
        <div className="bf-row">
          <button type="button" className="bf-btn" onClick={() => setAdding('invite')}>{t('Invite new member')}</button>
          <button type="button" className="bf-btn primary" onClick={() => setAdding('employee')}>{t('Add member')}</button>
        </div>
      </div>
      <UsersTabs active="employees" />
      <div className="bf-seg" role="group" aria-label={t('Role')}>
        {ROLE_SEG.map(([label, value]) => (
          <button key={label} type="button" className={role === value ? 'on' : undefined} aria-pressed={role === value} onClick={() => setRole(value)}>
            {t(label)}
          </button>
        ))}
      </div>

      <section className="bf-card" style={{ marginTop: 17 }}>
        <div className="bf-card-head">
          <h3>{t('User directory')}</h3>
          <div className="bf-row">
            <input
              className="bf-input strong"
              style={{ width: 330 }}
              type="search"
              placeholder={t('Search name, email or organisation')}
              aria-label={t('Search name, email or organisation')}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <div className="bf-anchor" ref={statusMenu.ref}>
              <button type="button" className="bf-btn" aria-haspopup="menu" aria-expanded={statusMenu.open} onClick={() => statusMenu.setOpen((o) => !o)}>
                {t(STATUS_OPTIONS.find(([v]) => v === status)?.[1] ?? 'Active')}
              </button>
              {statusMenu.open && (
                <div className="bf-menu" role="menu" style={{ right: 0, top: 40, minWidth: 110 }}>
                  {STATUS_OPTIONS.map(([value, label]) => (
                    <button key={value} type="button" role="menuitemradio" aria-checked={status === value} className={status === value ? 'item on' : 'item'} onClick={() => { setStatus(value); statusMenu.setOpen(false); }}>
                      {t(label)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {list.isError && (
          <p className="bf-error" role="alert" style={{ padding: '0 18px 12px' }}>
            {describeApiError(list.error, t('We couldn’t load users'))}{' '}
            <button type="button" className="bf-link" onClick={() => list.refetch()}>{t('Retry')}</button>
          </p>
        )}

        <table className="bf-users" aria-busy={list.isFetching}>
          <thead>
            <tr>
              <th style={{ width: '30%' }}>{t('Name')}</th>
              <th style={{ width: '13%' }}>{t('Status')}</th>
              <th style={{ width: '16%' }}>{t('Role')}</th>
              <th style={{ width: '20%' }}>{t('Organisation')}</th>
              <th>{t('Actions')}</th>
            </tr>
          </thead>
          <tbody>
            {list.isPending && <tr><td className="bf-empty" colSpan={5}>{t('Loading users')}</td></tr>}
            {list.data && !users.length && <tr><td className="bf-empty" colSpan={5}>{t('No users match your search.')}</td></tr>}
            {users.map((u) => (
              <tr key={u.id}>
                <td>
                  <div className="bf-person">
                    <span className="bf-av" aria-hidden="true">{initials(u.name)}</span>
                    <div><b>{u.name}</b><small>{u.email}</small></div>
                  </div>
                </td>
                <td>
                  <span className={u.is_active ? 'bf-status' : 'bf-status off'}>
                    {t(!u.is_active ? 'Inactive' : u.invite_pending ? 'Invited' : 'Active')}
                  </span>
                </td>
                <td>{t(u.role === 'client' ? 'Client contact' : ROLE_LABEL[u.role] ?? u.role)}</td>
                <td>{organisationOf(u)}</td>
                <td><Link className="bf-link" to={paths.adminUser(u.id)}>{t('View profile')}</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {adding === 'employee' && <NewEmployeeModal onClose={() => setAdding(null)} onCreated={(c) => { setAdding(null); setLink(c); }} />}
      {adding === 'invite' && <InviteMemberModal onClose={() => setAdding(null)} onCreated={(c) => { setAdding(null); setLink(c); }} />}
      {selected && <AccountModal key={selected.id} user={selected} onClose={() => navigate(paths.adminUsers)} onLink={setLink} />}
      {link && <ShareLinkModal name={link.user.name} email={link.user.email} url={link.invite.url} expiresAt={link.invite.expires_at} onClose={() => setLink(null)} />}
    </main>
  );
}

function NewEmployeeModal({ onClose, onCreated }: { onClose: () => void; onCreated: (c: CreatedUser) => void }) {
  const { t } = usePrefs();
  const create = useCreateUser();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<AssignableRole>('developer');
  const [jobTitle, setJobTitle] = useState('');
  const [joinDate, setJoinDate] = useState(today());
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
      onCreated(await create.mutateAsync({ name: name.trim(), email: email.trim(), role, join_date: joinDate || null, job_title: jobTitle.trim() || null }));
    } catch (e) {
      setError(describeApiError(e, t('That didn’t work. Try again.')));
    }
  };

  return (
    <Modal title="New employee" onClose={onClose} onSubmit={save}>
      <p className="bf-muted" style={{ marginTop: 6 }}>{t('Create an employee account and assign a role.')}</p>
      <div className="two">
        <Field label="Full name" error={tried ? errors.name : ''}>
          <input className="bf-input" type="text" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="off" />
        </Field>
        <Field label="Work email" error={tried ? errors.email : ''}>
          <input className="bf-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={320} autoComplete="off" />
        </Field>
      </div>
      <Field label="Role">
        <select value={role} onChange={(e) => setRole(e.target.value as AssignableRole)}>
          {ASSIGNABLE_ROLES.map((r) => <option key={r} value={r}>{t(ROLE_LABEL[r])}</option>)}
        </select>
      </Field>
      <div className="two">
        <Field label="Job title">
          <input className="bf-input" type="text" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} maxLength={100} autoComplete="off" />
        </Field>
        <Field label="Join date">
          <input className="bf-input" type="date" value={joinDate} onChange={(e) => setJoinDate(e.target.value)} />
        </Field>
      </div>
      {error && <p className="bf-error" role="alert">{error}</p>}
      <div className="foot">
        <button type="button" className="bf-btn" onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="bf-btn primary" disabled={create.isPending}>{t('Create employee')}</button>
      </div>
    </Modal>
  );
}

/** The server has no mailer: the account is created and its one-time sign-in link is handed to the administrator to send. */
function InviteMemberModal({ onClose, onCreated }: { onClose: () => void; onCreated: (c: CreatedUser) => void }) {
  const { t } = usePrefs();
  const create = useCreateUser();
  const [email, setEmail] = useState('');
  const [tried, setTried] = useState(false);
  const [error, setError] = useState('');
  const emailError = EMAIL_RE.test(email.trim()) ? '' : 'Enter a valid email address.';

  const save = async () => {
    setTried(true);
    setError('');
    if (emailError) return;
    const address = email.trim();
    const name = address.split('@')[0].split(/[._-]+/).filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(' ');
    try {
      onCreated(await create.mutateAsync({ name: name || address, email: address, role: 'developer' }));
    } catch (e) {
      setError(describeApiError(e, t('That didn’t work. Try again.')));
    }
  };

  return (
    <Modal title="Invite new member" width={480} onClose={onClose} onSubmit={save}>
      <p className="bf-muted" style={{ margin: '8px 0' }}>{t('Send a sign-in link to the member’s email address.')}</p>
      <Field label="Email address" error={tried ? emailError : ''}>
        <input className="bf-input" type="email" placeholder="new.member@example.com" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={320} autoComplete="off" />
      </Field>
      {error && <p className="bf-error" role="alert">{error}</p>}
      <div className="bf-row" style={{ justifyContent: 'flex-end', marginTop: 16 }}>
        <button type="button" className="bf-btn" onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="bf-btn primary" disabled={create.isPending}>{t('Send invitation')}</button>
      </div>
    </Modal>
  );
}

function AccountModal({ user, onClose, onLink }: { user: AdminUser; onClose: () => void; onLink: (c: CreatedUser) => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const update = useUpdateUser();
  const setActive = useSetUserActive();
  const newInvite = useNewInvite();
  const orgs = useOrganisations().data?.items ?? [];

  const client = user.role === 'client';
  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const [role, setRole] = useState(user.role);
  const [jobTitle, setJobTitle] = useState(user.job_title ?? '');
  const [joinDate, setJoinDate] = useState(user.join_date ?? '');
  const [tried, setTried] = useState(false);
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState(false);

  const errors = {
    name: name.trim() ? '' : 'Enter a name.',
    email: EMAIL_RE.test(email.trim()) ? '' : 'Enter a valid email address.',
  };
  const busy = update.isPending || setActive.isPending || newInvite.isPending;
  const fail = (e: unknown) => setError(describeApiError(e, t('That didn’t work. Try again.')));
  const looksAfter = user.role === 'account_manager' ? orgs.filter((o) => o.account_managers.some((m) => m.id === user.id)).map((o) => o.name) : [];

  const save = async () => {
    setTried(true);
    setError('');
    if (errors.name || errors.email) return;
    try {
      await update.mutateAsync({
        id: user.id,
        name: name.trim(),
        email: email.trim(),
        join_date: joinDate || null,
        job_title: jobTitle.trim(),
        role: role as AssignableRole,
      });
      toast.success('User updated.');
      onClose();
    } catch (e) {
      fail(e);
    }
  };

  const toggle = async () => {
    setConfirming(false);
    setError('');
    try {
      await setActive.mutateAsync({ id: user.id, active: !user.is_active });
      toast.success(user.is_active ? 'User deactivated.' : 'User activated.');
    } catch (e) {
      fail(e);
    }
  };

  const signIn = async () => {
    setError('');
    try {
      onLink(await newInvite.mutateAsync(user.id));
    } catch (e) {
      fail(e);
    }
  };

  return (
    <>
    <Modal title="Account details" onClose={onClose} onSubmit={client ? undefined : save}>
      <div className="bf-who-row">
        <span className="bf-badge">{initials(user.name)}</span>
        {user.name}
        <span className="bf-pill">{t(user.is_active ? 'Active' : 'Inactive')}</span>
      </div>
      <Field label="Full name" error={tried ? errors.name : ''}>
        <input className="bf-input" type="text" value={name} readOnly={client} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="off" />
      </Field>
      <Field label="Work email" error={tried ? errors.email : ''}>
        <input className="bf-input" type="email" value={email} readOnly={client} onChange={(e) => setEmail(e.target.value)} maxLength={320} autoComplete="off" />
      </Field>
      {!client && (
        <>
          <Field label="Role">
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {!ASSIGNABLE_ROLES.includes(role as AssignableRole) && <option value={role}>{t(ROLE_LABEL[role] ?? role)}</option>}
              {ASSIGNABLE_ROLES.map((r) => <option key={r} value={r}>{t(ROLE_LABEL[r])}</option>)}
            </select>
          </Field>
          {user.role === 'account_manager' && (
            <div className="bf-field">
              {t('Clients they look after')}<br />
              <span className="bf-pill" style={{ marginTop: 6, fontWeight: 600, padding: '7px 13px' }}>{looksAfter.join(' · ') || '–'}</span>
            </div>
          )}
          <div className="two">
            <Field label="Job title">
              <input className="bf-input" type="text" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} maxLength={100} autoComplete="off" />
            </Field>
            <Field label="Join date">
              <input className="bf-input" type="date" value={joinDate} onChange={(e) => setJoinDate(e.target.value)} />
            </Field>
          </div>
        </>
      )}
      <div className="bf-acc">
        <span>{t('Account access')}</span>
        <button type="button" className="bf-btn danger" disabled={busy} onClick={user.is_active ? () => setConfirming(true) : toggle}>{t(user.is_active ? 'Deactivate' : 'Activate')}</button>
        <button type="button" className="bf-btn" disabled={busy} onClick={signIn}>{t('Manage sign-in')}</button>
      </div>
      {error && <p className="bf-error" role="alert">{error}</p>}
      <div className="foot">
        <button type="button" className="bf-btn" onClick={onClose}>{t('Cancel')}</button>
        {!client && <button type="submit" className="bf-btn primary" disabled={busy}>{t('Save changes')}</button>}
      </div>
    </Modal>
      {confirming && (
        <ConfirmModal
          title="Deactivate?"
          text="Deactivating this account suspends project access. You can activate it again later."
          confirm="Deactivate"
          onConfirm={toggle}
          onCancel={() => setConfirming(false)}
        />
      )}
    </>
  );
}
