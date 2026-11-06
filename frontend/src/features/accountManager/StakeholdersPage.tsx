import { useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Dialog, EMAIL_RE, Field } from '@/features/admin/Dialog';
import { initialsOf } from '@/features/client/format';
import { useProjectContext } from '@/features/client/ClientProjectLayout';
import { EmptyCard } from '@/features/client/ui';
import type { ClientContact } from '@/features/client/types';

/** Stakeholders tab: the project's contacts, which an Account Manager can edit. */
export function StakeholdersPage() {
  const { project } = useProjectContext();
  const { t } = usePrefs();
  // The backend has no stakeholder endpoint yet: edits live in this session only.
  const [edits, setEdits] = useState<Record<string, ClientContact>>({});
  const [editing, setEditing] = useState<ClientContact | null>(null);
  const people = project.contacts.map((c) => edits[c.email] ?? c);

  return (
    <>
      <h2 className="cp-section-title">{t('Stakeholders')}</h2>
      <p className="cp-section-sub">{t('Contact your Project Manager for delivery questions and shared updates.')}</p>
      {!people.length && <EmptyCard />}
      {people.map((c) => (
        <article className="cp-contact" key={c.name + project.id}>
          <div className="cp-contact-head">
            <span className="cp-contact-initials" aria-hidden="true">{initialsOf(c.name)}</span>
            <h3 className="cp-contact-name">{c.name}</h3>
            <span className="cp-contact-role">{t(c.role)}</span>
            <button type="button" className="ad-link" style={{ marginLeft: 'auto' }} onClick={() => setEditing(c)}>
              {t('Edit')}
            </button>
          </div>
          <a className="cp-contact-email" href={`mailto:${c.email}`}>{c.email}</a>
          <p className="cp-contact-tel">{t('Tel: {phone}', { phone: c.phone || '-' })}</p>
        </article>
      ))}
      {editing && (
        <EditDialog
          person={editing}
          onClose={() => setEditing(null)}
          onSave={(next) => {
            setEdits((e) => ({ ...e, [project.contacts.find((c) => c.name === editing.name)?.email ?? editing.email]: next }));
            setEditing(null);
          }}
        />
      )}
    </>
  );
}

function EditDialog({ person, onClose, onSave }: { person: ClientContact; onClose: () => void; onSave: (c: ClientContact) => void }) {
  const { t } = usePrefs();
  const [email, setEmail] = useState(person.email);
  const [phone, setPhone] = useState(person.phone ?? '');
  const [tried, setTried] = useState(false);
  const invalid = !EMAIL_RE.test(email.trim());

  return (
    <Dialog
      title="Edit stakeholder"
      onClose={onClose}
      onSubmit={() => {
        setTried(true);
        if (!invalid) onSave({ ...person, email: email.trim(), phone: phone.trim() || undefined });
      }}
    >
      <Field label="Email" error={tried && invalid ? 'Enter a valid email address.' : ''}>
        <input className="ad-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={200} autoComplete="off" />
      </Field>
      <Field label="Phone number">
        <input className="ad-input" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={40} autoComplete="off" />
      </Field>
      <div className="ad-actions">
        <button type="button" className="ad-btn ad-btn--ghost" onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="ad-btn">{t('Save changes')}</button>
      </div>
    </Dialog>
  );
}
