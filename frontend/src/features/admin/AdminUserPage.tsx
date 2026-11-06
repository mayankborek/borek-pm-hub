import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import {
  ASSIGNABLE_ROLES,
  ROLE_LABEL,
  useAdminUsers,
  useNewInvite,
  useSetUserActive,
  useUpdateUser,
  type AdminUser,
  type AssignableRole,
} from './adminApi';
import { Back } from './Back';
import { ConfirmDialog, EMAIL_RE, Field } from './Dialog';

export function AdminUserPage() {
  const { t } = usePrefs();
  const { userId = '' } = useParams();
  const list = useAdminUsers('', '', 'all');
  const user = list.data?.items.find((u) => u.id === userId);

  if (!user) {
    return (
      <>
        <Back to={paths.adminUsers} label="Users" />
        <h2 className="ad-title ad-gap">{t(list.isPending ? 'Loading users' : 'User not found')}</h2>
        {list.data && <p className="ad-meta">{t('It may have been removed. Go back to the user directory.')}</p>}
      </>
    );
  }
  return <UserDetail key={user.id} user={user} />;
}

function UserDetail({ user }: { user: AdminUser }) {
  const { t } = usePrefs();
  const toast = useToast();
  const navigate = useNavigate();
  const update = useUpdateUser();
  const setActive = useSetUserActive();
  const newInvite = useNewInvite();

  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const [role, setRole] = useState(user.role);
  const [joinDate, setJoinDate] = useState(user.join_date ?? '');
  const [tried, setTried] = useState(false);
  const [error, setError] = useState('');
  const [confirm, setConfirm] = useState<'deactivate' | 'link' | null>(null);

  const errors = {
    name: name.trim() ? '' : 'Enter a name.',
    email: EMAIL_RE.test(email.trim()) ? '' : 'Enter a valid email address.',
  };
  const busy = update.isPending || setActive.isPending || newInvite.isPending;
  // Roles outside the assignable set (e.g. client) are shown but cannot be changed here.
  const roleLocked = !ASSIGNABLE_ROLES.includes(user.role as AssignableRole);
  const fail = (e: unknown) => setError(describeApiError(e, t('That didn’t work. Try again.')));

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
        ...(roleLocked ? {} : { role: role as AssignableRole }),
      });
      toast.success('User updated.');
      navigate(paths.adminUsers);
    } catch (e) {
      fail(e);
    }
  };

  const toggle = async () => {
    setConfirm(null);
    setError('');
    try {
      await setActive.mutateAsync({ id: user.id, active: !user.is_active });
      toast.success(user.is_active ? 'User deactivated.' : 'User activated.');
    } catch (e) {
      fail(e);
    }
  };

  const createLink = async () => {
    setConfirm(null);
    setError('');
    try {
      const created = await newInvite.mutateAsync(user.id);
      navigate(paths.adminUserInvitation(user.id), { state: { created } });
    } catch (e) {
      fail(e);
    }
  };

  return (
    <>
      <Back to={paths.adminUsers} label="Users" />
      <div className="ad-head ad-gap">
        <h2 className="ad-title ad-title--lg">{user.name}</h2>
        <div className="ad-head-actions">
          <button type="button" className="ad-btn ad-btn--ghost" disabled={busy} onClick={user.is_active ? () => setConfirm('deactivate') : toggle}>{t(user.is_active ? 'Deactivate' : 'Activate')}</button>
          <button type="button" className="ad-btn" disabled={busy} onClick={() => setConfirm('link')}>{t('Create new link')}</button>
        </div>
      </div>

      <form className="ad-card ad-card--form" noValidate onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <h3>{t('Account details')}</h3>
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
          <select className="ad-input" value={role} onChange={(e) => setRole(e.target.value)} disabled={roleLocked}>
            {roleLocked && <option value={role}>{t(ROLE_LABEL[role] ?? role)}</option>}
            {ASSIGNABLE_ROLES.map((r) => <option key={r} value={r}>{t(ROLE_LABEL[r])}</option>)}
          </select>
        </Field>
        <Field label="Account status">
          <input className="ad-input" readOnly value={t(user.is_active ? 'Active' : 'Inactive')} />
        </Field>
        {error && <p className="ad-error" role="alert">{error}</p>}
        <div className="ad-actions">
          <button type="button" className="ad-link" onClick={() => navigate(paths.adminUsers)}>{t('Cancel')}</button>
          <button type="submit" className="ad-btn" disabled={busy}>{t('Save changes')}</button>
        </div>
      </form>

      {confirm === 'deactivate' && (
        <ConfirmDialog
          title="Deactivate?"
          text="Deactivating this account suspends project access. You can activate it again later."
          confirm="Deactivate"
          onConfirm={toggle}
          onCancel={() => setConfirm(null)}
        />
      )}
      {confirm === 'link' && (
        <ConfirmDialog
          title="Create new link?"
          text="The old link will stop working. The user's account information and role will stay the same."
          confirm="Create new link"
          onConfirm={createLink}
          onCancel={() => setConfirm(null)}
        />
      )}
    </>
  );
}
