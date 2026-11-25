import { useState } from 'react';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf } from '@/features/client/format';
import { useProjectContext } from '@/features/client/ClientProjectLayout';
import { Icon } from '@/features/client/icons';
import { EmptyCard } from '@/features/client/ui';
import { StakeholderDialog } from '@/features/client/StakeholderDialog';
import type { ClientContact } from '@/features/client/types';
import './manager.css';

const isBorek = (c: ClientContact) => c.email.toLowerCase().endsWith('@boreksolutions.com');

/** Stakeholders tab (borek_screens.html): a Borek team card and a client contact card. Stakeholders of the register can be added and edited. */
export function ManagerStakeholdersPage() {
  const { project } = useProjectContext();
  const { t } = usePrefs();
  // `null` = closed, a contact = editing it.
  const [dialog, setDialog] = useState<{ person?: ClientContact } | null>(null);

  return (
    <>
      <div className="mg-head">
        <div>
          <h2 className="cp-section-title">{t('Project stakeholders')}</h2>
          <p className="cp-section-sub">{t('Your key contacts for project delivery and client coordination.')}</p>
        </div>
      </div>
      {!project.contacts.length && <EmptyCard />}
      <div className="mg-people">
        {project.contacts.map((c) => {
          const borek = isBorek(c);
          return (
            <article className="mg-person" key={c.stakeholderId ?? c.email + c.name}>
              <div className="mg-kind">
                <span>{t(borek ? 'Borek team' : 'Client contact')}</span>
                <span>{borek ? 'Borek Solutions' : project.organisation ?? project.name}</span>
              </div>
              <div className="mg-who">
                <span className="mg-ini" aria-hidden="true">{initialsOf(c.name)}</span>
                <div><h3>{c.name}</h3><p>{t(c.role)}</p></div>
              </div>
              <dl className="mg-detail">
                <div>
                  <span className="mg-dico"><Icon name="mail" className="cx-ico" strokeWidth={1.5} /></span>
                  <div><dt>{t('Work email')}</dt><dd>{c.email || '–'}</dd></div>
                </div>
                <div>
                  <span className="mg-dico"><Icon name="phone" className="cx-ico" strokeWidth={1.5} /></span>
                  <div><dt>{t('Phone')}</dt><dd>{c.phone || t('Not provided')}</dd></div>
                </div>
              </dl>
              <div className="mg-foot">
                <span>{t(borek ? 'Delivery contact' : 'Client organisation contact')}</span>
                {borek && c.stakeholderId && (
                  <button type="button" className="mg-btn" onClick={() => setDialog({ person: c })}>{t('Edit contact')}</button>
                )}
              </div>
            </article>
          );
        })}
      </div>
      {dialog && <StakeholderDialog projectId={project.id} person={dialog.person} onClose={() => setDialog(null)} />}
    </>
  );
}
