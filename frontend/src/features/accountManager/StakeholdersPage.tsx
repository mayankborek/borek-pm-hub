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
  const [editing, setEditing] = useState<{ key: string; person: ClientContact } | null>(null);
  const people = project.contacts.map((c) => ({ key: c.email, person: edits[c.email] ?? c }));

  return (
    <>
      <h2 className="cp-section-title">{t('Stakeholders')}</h2>
      <p className="cp-section-sub">{t('Contact your Project Manager for delivery questions and shared updates.')}</p>
      {!people.length && <EmptyCard />}
      {people.map(({ key, person: c }) => (
        <article className="cp-contact" key={key + project.id}>
          <div className="cp-contact-head">
            <span className="cp-contact-initials" aria-hidden="true">{initialsOf(c.name)}</span>
            <h3 className="cp-contact-name">{c.name}</h3>
            <span className="cp-contact-role">{t(c.role)}</span>
            <button type="button" className="ad-link" style={{ marginLeft: 'auto' }} onClick={() => setEditing({ key, person: c })}>
              {t('Edit')}
            </button>
          </div>
          <a className="cp-contact-email" href={`mailto:${c.email}`}>{c.email}</a>
          <p className="cp-contact-tel">{t('Tel: {phone}', { phone: c.phone || '-' })}</p>
        </article>
      ))}
      {editing && (
        <EditDialog
          person={editing.person}
          onClose={() => setEditing(null)}
          onSave={(next) => {
            setEdits((e) => ({ ...e, [editing.key]: next }));
            setEditing(null);
          }}
        />
      )}
    </>
  );
}

function EditDialog({ person, onClose, onSave }: { person: ClientContact; onClose: () => void; onSave: (c: ClientContact) => void }) {
  const { t } = usePrefs();
  const [name, setName] = useState(person.name);
  const [role, setRole] = useState(person.role);
  const [email, setEmail] = useState(person.email);
  const [phone, setPhone] = useState(person.phone ?? '');
  const [tried, setTried] = useState(false);
  const nameMissing = !name.trim();
  const invalid = !EMAIL_RE.test(email.trim());

  return (
    <Dialog
      title="Edit stakeholder"
      onClose={onClose}
      onSubmit={() => {
        setTried(true);
        if (!invalid && !nameMissing) onSave({ ...person, name: name.trim(), role: role.trim(), email: email.trim(), phone: phone.trim() || undefined });
      }}
    >
      <Field label="Full name" error={tried && nameMissing ? 'Full name is required.' : ''}>
        <input className="ad-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} autoComplete="off" />
      </Field>
      <Field label="Role">
        <input className="ad-input" value={role} onChange={(e) => setRole(e.target.value)} maxLength={120} autoComplete="off" />
      </Field>
      <Field label="Email" error={tried && invalid ? 'Enter a valid email address.' : ''}>
        <input className="ad-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={200} autoComplete="off" />
      </Field>
      <Field label="Phone">
        <input className="ad-input" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={40} autoComplete="off" />
      </Field>
      <div className="ad-actions">
        <button type="button" className="ad-btn ad-btn--ghost" onClick={onClose}>{t('Cancel')}</button>
        <button type="submit" className="ad-btn">{t('Save')}</button>
      </div>
    </Dialog>
  );
}
