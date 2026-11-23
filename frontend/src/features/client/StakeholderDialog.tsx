import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api, describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { Dialog, EMAIL_RE, Field } from '@/features/admin/Dialog';
import type { ClientContact } from './types';

/**
 * Saves one stakeholder of a project: a contact with a `stakeholderId` is changed (PATCH, sending the
 * version it was read at so a concurrent edit is refused), otherwise a new one is added (POST).
 * Contacts without an id (the project leads) come from the team, not the register, and are not editable.
 */
function useSaveStakeholder(projectId: string, person?: ClientContact) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { name: string; role: string; email: string; phone: string }) => {
      const fields = { name: v.name, role_title: v.role || null, email: v.email, phone: v.phone || null };
      return person?.stakeholderId
        ? api(`/projects/${projectId}/stakeholders/${person.stakeholderId}`, {
            method: 'PATCH',
            body: JSON.stringify({ ...fields, version: person.version }),
          })
        : api(`/projects/${projectId}/stakeholders`, { method: 'POST', body: JSON.stringify(fields) });
    },
    // The portal is rebuilt from the register, so refetching shows the saved contact.
    onSuccess: () => qc.invalidateQueries({ queryKey: ['client-portal'] }),
  });
}

/** Add (no `person`) or edit a stakeholder. Stays open with the server's message when the save fails. */
export function StakeholderDialog({ projectId, person, onClose }: { projectId: string; person?: ClientContact; onClose: () => void }) {
  const { t } = usePrefs();
  const toast = useToast();
  const save = useSaveStakeholder(projectId, person);
  const [name, setName] = useState(person?.name ?? '');
  const [role, setRole] = useState(person?.role ?? '');
  const [email, setEmail] = useState(person?.email ?? '');
  const [phone, setPhone] = useState(person?.phone ?? '');
  const [tried, setTried] = useState(false);
  const [error, setError] = useState<string>();
  const nameMissing = !name.trim();
  const invalid = !EMAIL_RE.test(email.trim());

  const submit = () => {
    setTried(true);
    setError(undefined);
    if (invalid || nameMissing) return;
    save.mutate(
      { name: name.trim(), role: role.trim(), email: email.trim(), phone: phone.trim() },
      {
        onSuccess: () => {
          toast.success(t(person ? 'Stakeholder saved' : 'Stakeholder added'));
          onClose();
        },
        onError: (err) => setError(describeApiError(err, t('The stakeholder could not be saved.'))),
      },
    );
  };

  return (
    <Dialog title={person ? 'Edit stakeholder' : 'Add stakeholder'} onClose={onClose} onSubmit={submit}>
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
      {error && <p className="field-error" role="alert">{error}</p>}
      <div className="ad-actions">
        <button type="button" className="ad-btn ad-btn--ghost" onClick={onClose} disabled={save.isPending}>{t('Cancel')}</button>
        <button type="submit" className="ad-btn" disabled={save.isPending}>{save.isPending ? t('Saving…') : t('Save changes')}</button>
      </div>
    </Dialog>
  );
}
