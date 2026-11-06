import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { EMAIL_RE, Dialog, Field } from './Dialog';
import { OrganisationDialog } from './AdminOrganisationsPage';
import { Back } from './Back';
import { orgActions, useOrganisation } from './adminStore';

export function AdminOrganisationPage() {
  const { t } = usePrefs();
  const toast = useToast();
  const { orgId = '' } = useParams();
  const org = useOrganisation(orgId);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);

  if (!org) {
    return (
      <>
        <Back to={paths.adminOrganisations} label="Organisations" />
        <h2 className="ad-title ad-gap">{t('Organisation not found')}</h2>
        <p className="ad-meta">{t('It may have been removed. Go back to the organisation directory.')}</p>
      </>
    );
  }

  const target = org.members.find((m) => m.id === removing);

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
        {!org.active && <span className="ad-tag">{t('Inactive')}</span>}
      </p>

      <ul className="ad-members">
        {!org.members.length && <li className="ad-empty-row">{t('No members yet.')}</li>}
        {org.members.map((m) => (
          <li className="ad-member" key={m.id}>
            <span>{m.name}</span>
            <span>{m.email}</span>
            <span>{t('Client contact')}</span>
            <button type="button" className="ad-link" aria-label={`${t('Remove')} ${m.name}`} onClick={() => setRemoving(m.id)}>{t('Remove')}</button>
          </li>
        ))}
      </ul>

      {adding && (
        <MemberDialog
          existing={org.members.map((m) => m.email.toLowerCase())}
          onClose={() => setAdding(false)}
          onSave={(name, email) => {
            orgActions.addMember(org.id, name, email);
            toast.success('Member added.');
          }}
        />
      )}
      {editing && (
        <OrganisationDialog
          org={org}
          onClose={() => setEditing(false)}
          onSave={(name, accountManager, active) => orgActions.update(org.id, { name, accountManager, active })}
        />
      )}
      {target && (
        <Dialog title="Remove member?" onClose={() => setRemoving(null)}>
          <p className="ad-hint">{t('{name} will no longer belong to {org}.', { name: target.name, org: org.name })}</p>
          <div className="ad-actions">
            <button type="button" className="ad-btn ad-btn--ghost" onClick={() => setRemoving(null)}>{t('Cancel')}</button>
            <button
              type="button"
              className="ad-btn ad-btn--danger-fill"
              onClick={() => {
                orgActions.removeMember(org.id, target.id);
                setRemoving(null);
                toast.success('Member removed.');
              }}
            >
              {t('Remove')}
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}

function MemberDialog({ existing, onClose, onSave }: { existing: string[]; onClose: () => void; onSave: (name: string, email: string) => void }) {
  const { t } = usePrefs();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [tried, setTried] = useState(false);

  const errors = {
    name: name.trim() ? '' : 'Enter a name.',
    email: !EMAIL_RE.test(email.trim()) ? 'Enter a valid email address.' : existing.includes(email.trim().toLowerCase()) ? 'This person is already a member.' : '',
  };

  const save = () => {
    setTried(true);
    if (errors.name || errors.email) return;
    onSave(name.trim(), email.trim());
    onClose();
  };

  return (
    <Dialog title="Add member" onClose={onClose} onSubmit={save}>
      <Field label="Name" error={tried ? errors.name : ''}>
        <input className="ad-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="off" />
      </Field>
      <Field label="Email" error={tried ? errors.email : ''}>
        <input className="ad-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={320} autoComplete="off" />
      </Field>
      <div className="ad-actions">
        <button type="button" className="ad-btn ad-btn--ghost" onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="ad-btn">{t('Add member')}</button>
      </div>
    </Dialog>
  );
}
