import { useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf } from '@/features/client/format';
import { useProjectContext } from '@/features/client/ClientProjectLayout';
import { EmptyCard } from '@/features/client/ui';
import { StakeholderDialog } from '@/features/client/StakeholderDialog';
import type { ClientContact } from '@/features/client/types';

/** Stakeholders tab: the project's contacts. Stakeholders of the register can be added and edited. */
export function StakeholdersPage() {
  const { project } = useProjectContext();
  const { t } = usePrefs();
  // `null` = closed, `{}` = adding, a contact = editing it.
  const [dialog, setDialog] = useState<{ person?: ClientContact } | null>(null);

  return (
    <>
      <h2 className="cp-section-title">{t('Stakeholders')}</h2>
      <p className="cp-section-sub">{t('Contact your Project Manager for delivery questions and shared updates.')}</p>
      <button type="button" className="ad-btn" onClick={() => setDialog({})}>{t('Add stakeholder')}</button>
      {!project.contacts.length && <EmptyCard />}
      {project.contacts.map((c) => (
        <article className="am-sh" key={c.stakeholderId ?? c.email + c.name}>
          <div className="am-sh-head">
            <span className="am-sh-initials" aria-hidden="true">{initialsOf(c.name)}</span>
            <h3 className="am-sh-name">{c.name}</h3>
            <span className="am-sh-role">{t(c.role)}</span>
            {c.stakeholderId && (
              <button type="button" className="ad-link am-sh-edit" onClick={() => setDialog({ person: c })}>
                {t('Edit')}
              </button>
            )}
          </div>
          {c.email ? <a className="am-sh-email" href={`mailto:${c.email}`}>{c.email}</a> : <span className="am-sh-email">–</span>}
          <p className="am-sh-tel">{t('Tel: {phone}', { phone: c.phone || '-' })}</p>
        </article>
      ))}
      {dialog && <StakeholderDialog projectId={project.id} person={dialog.person} onClose={() => setDialog(null)} />}
    </>
  );
}
