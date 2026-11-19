import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { EMAIL_RE, ConfirmDialog, Dialog, Field } from './Dialog';
import { OrganisationDialog } from './AdminOrganisationsPage';
import { Back } from './Back';
import {
  useAddMember,
  useOrgMembers,
  useOrganisation,
  useRemoveMember,
  useRenewMemberInvite,
  type CreatedMember,
  type MemberStatus,
} from './organisationsApi';

const STATUS_LABEL: Record<MemberStatus, string> = {
  invited: 'Invited',
  invite_expired: 'Invite expired',
  active: 'Active',
  deactivated: 'Inactive',
};

export function AdminOrganisationPage() {
  const { t } = usePrefs();
  const toast = useToast();
  const { orgId = '' } = useParams();
  const orgQuery = useOrganisation(orgId);
  const org = orgQuery.data;
  const members = useOrgMembers(orgId);
  const add = useAddMember(orgId);
  const renew = useRenewMemberInvite(orgId);
  const remove = useRemoveMember(orgId);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [link, setLink] = useState<CreatedMember | null>(null);

  if (orgQuery.isPending) return <p className="ad-meta">{t('Loading organisations')}</p>;
  if (!org) {
    return (
      <>
        <Back to={paths.adminOrganisations} label="Organisations" />
        <h2 className="ad-title ad-gap">{t('Organisation not found')}</h2>
        <p className="ad-meta">{t('It may have been removed. Go back to the organisation directory.')}</p>
      </>
    );
  }

  const people = members.data?.items ?? [];
  const target = people.find((m) => m.id === removing);

  const newLink = async (userId: string) => {
    try {
      setLink(await renew.mutateAsync(userId));
    } catch (e) {
      toast.error(describeApiError(e, t('That didn’t work. Try again.')));
    }
  };

  return (
    <>
      <Back to={paths.adminOrganisations} label="Organisations" />
      <div className="ad-head ad-gap">
        <h2 className="ad-title ad-title--lg">{org.name}</h2>
        <div className="ad-head-actions">
          <button type="button" className="ad-link" onClick={() => setEditing(true)}>{t('Edit details')}</button>
          <button type="button" className="ad-btn" onClick={() => setAdding(true)}>{t('Add member')}</button>
        </div>
      </div>
      <p className="ad-meta">
        {t('Members · Manage who belongs to this organisation.')}
        {org.archived_at && <span className="ad-tag">{t('Inactive')}</span>}
      </p>

      <ul className="ad-members">
        {members.isPending && <li className="ad-empty-row">{t('Loading users')}</li>}
        {members.data && !people.length && <li className="ad-empty-row">{t('No members yet.')}</li>}
        {people.map((m) => (
          <li className="ad-member" key={m.id}>
            <span>{m.name}</span>
            <span>{m.email}</span>
            <span>
              {t(m.job_title ?? 'Client contact')}
              <span className="ad-tag">{t(STATUS_LABEL[m.status])}</span>
            </span>
            <span>
              {(m.status === 'invited' || m.status === 'invite_expired') && (
                <button type="button" className="ad-link" onClick={() => newLink(m.id)}>{t('New invite link')}</button>
              )}{' '}
              {m.status !== 'deactivated' && (
                <button type="button" className="ad-link" aria-label={`${t('Remove')} ${m.name}`} onClick={() => setRemoving(m.id)}>{t('Remove')}</button>
              )}
            </span>
          </li>
        ))}
      </ul>

      {adding && (
        <MemberDialog
          existing={people.map((m) => m.email.toLowerCase())}
          onClose={() => setAdding(false)}
          onSave={async (name, email, jobTitle) => {
            setLink(await add.mutateAsync({ name, email, job_title: jobTitle || null }));
            setAdding(false);
          }}
        />
      )}
      {link && <InviteLinkDialog created={link} onClose={() => setLink(null)} />}
      {editing && <OrganisationDialog org={org} onClose={() => setEditing(false)} />}
      {target && (
        <ConfirmDialog
          title="Remove member?"
          text={t('{name} will no longer belong to {org}.', { name: target.name, org: org.name })}
          confirm="Remove"
          busy={remove.isPending}
          onCancel={() => setRemoving(null)}
          onConfirm={async () => {
            try {
              await remove.mutateAsync(target.id);
              toast.success('Member removed.');
            } catch (e) {
              toast.error(describeApiError(e, t('That didn’t work. Try again.')));
            }
            setRemoving(null);
          }}
        />
      )}
    </>
  );
}

function MemberDialog({
  existing,
  onClose,
  onSave,
}: {
  existing: string[];
  onClose: () => void;
  onSave: (name: string, email: string, jobTitle: string) => Promise<void>;
}) {
  const { t } = usePrefs();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [jobTitle, setJobTitle] = useState('');
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const errors = {
    name: name.trim() ? '' : 'Enter a name.',
    email: !EMAIL_RE.test(email.trim()) ? 'Enter a valid email address.' : existing.includes(email.trim().toLowerCase()) ? 'This person is already a member.' : '',
  };

  const save = async () => {
    setTried(true);
    setError('');
    if (errors.name || errors.email) return;
    setBusy(true);
    try {
      await onSave(name.trim(), email.trim(), jobTitle.trim());
    } catch (e) {
      setError(describeApiError(e, t('That didn’t work. Try again.')));
      setBusy(false);
    }
  };

  return (
    <Dialog title="Add member" onClose={onClose} onSubmit={save}>
      <Field label="Name" error={tried ? errors.name : ''}>
        <input className="ad-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="off" />
      </Field>
      <Field label="Email" error={tried ? errors.email : ''}>
        <input className="ad-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={320} autoComplete="off" />
      </Field>
      <Field label="Job title">
        <input className="ad-input" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} maxLength={100} autoComplete="off" />
      </Field>
      <p className="ad-hint">{t('We’ll create the client account and give you a one-time invitation link to share.')}</p>
      {error && <p className="ad-error" role="alert">{error}</p>}
      <div className="ad-actions">
        <button type="button" className="ad-btn ad-btn--ghost" onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="ad-btn" disabled={busy}>{t('Create account')}</button>
      </div>
    </Dialog>
  );
}

/** The server shows an invitation link once, so this is the only chance to copy it. */
function InviteLinkDialog({ created, onClose }: { created: CreatedMember; onClose: () => void }) {
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
    <Dialog title="Share invitation link" onClose={onClose}>
      <p className="ad-card-sub">{created.member.name} · {created.member.email}</p>
      <div className="ad-copy">
        <input className="ad-copy-field" readOnly value={created.invite.url} aria-label={t('Sign-in link')} onFocus={(e) => e.currentTarget.select()} />
        <button type="button" className="ad-btn ad-btn--ghost" onClick={copy}>{t(copied ? 'Copied' : 'Copy')}</button>
      </div>
      <p className="ad-hint">{t('Send this to the person yourself: on mail or on Teams.')}</p>
      <p className="ad-hint">{t('It works once and expires on {date}. It won’t be shown again.', { date: expires })}</p>
      <div className="ad-actions">
        <button type="button" className="ad-btn" onClick={onClose}>{t('Done')}</button>
      </div>
    </Dialog>
  );
}
