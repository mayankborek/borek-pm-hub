import { useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { Dialog, EMAIL_RE, Field } from '@/features/admin/Dialog';
import { initialsOf } from '@/features/client/format';
import { useProjectContext } from '@/features/client/ClientProjectLayout';
import { EmptyCard } from '@/features/client/ui';
import type { ClientContact } from '@/features/client/types';
import './manager.css';

const isBorek = (c: ClientContact) => c.email.toLowerCase().endsWith('@boreksolutions.com');

/** Stakeholders tab (borek_screens.html): a Borek team card and a client contact card, each editable. */
export function ManagerStakeholdersPage() {
  const { project } = useProjectContext();
  const { t } = usePrefs();
  // The backend has no stakeholder endpoint yet: edits live in this session only.
  const [edits, setEdits] = useState<Record<string, ClientContact>>({});
  const [editing, setEditing] = useState<{ key: string; person: ClientContact } | null>(null);
  const people = project.contacts.map((c) => ({ key: c.email, person: edits[c.email] ?? c }));

  return (
    <>
      <h2 className="cp-section-title">{t('Project stakeholders')}</h2>
      <p className="cp-section-sub">{t('Your key contacts for project delivery and client coordination.')}</p>
      {!people.length && <EmptyCard />}
      <div className="mg-people">
        {people.map(({ key, person: c }) => {
          const borek = isBorek(c);
          return (
            <article className="mg-person" key={key + project.id}>
              <div className="mg-kind">
                <span>{t(borek ? 'Borek team' : 'Client contact')}</span>
                <span>{borek ? 'Borek Solutions' : project.name}</span>
              </div>
              <div className="mg-who">
                <span className="mg-ini" aria-hidden="true">{initialsOf(c.name)}</span>
                <div><h3>{c.name}</h3><p>{t(c.role)}</p></div>
              </div>
              <dl className="mg-detail">
                <div><dt>{t('Work email')}</dt><dd>{c.email}</dd></div>
                <div><dt>{t('Phone')}</dt><dd>{c.phone || t('Not provided')}</dd></div>
              </dl>
              <div className="mg-foot">
                <span>{t(borek ? 'Delivery contact' : 'Client organisation contact')}</span>
                <button type="button" className="mg-btn" onClick={() => setEditing({ key, person: c })}>{t('Edit contact')}</button>
              </div>
            </article>
          );
        })}
      </div>
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
      <Field label="Work email" error={tried && invalid ? 'Enter a valid email address.' : ''}>
        <input className="ad-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={200} autoComplete="off" />
      </Field>
      <Field label="Phone">
        <input className="ad-input" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={40} autoComplete="off" />
      </Field>
    </Dialog>
  );
}
