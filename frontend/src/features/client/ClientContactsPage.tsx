import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf } from './format';
import { useProjectContext } from './ClientProjectLayout';
import { EmptyCard } from './ui';

export function ClientContactsPage() {
  const { project } = useProjectContext();
  const { t } = usePrefs();

  return (
    <>
      <h2 className="cp-section-title">{t('Project contacts')}</h2>
      <p className="cp-section-sub">{t('Contact your Project Manager for delivery questions and shared updates.')}</p>
      {!project.contacts.length && <EmptyCard />}
      {project.contacts.map((c) => (
        <article className="cp-contact" key={c.email}>
          <div className="cp-contact-person">
            <span className="cp-contact-initials" aria-hidden="true">{initialsOf(c.name)}</span>
            <div>
              <h3 className="cp-contact-name">{c.name}</h3>
              <p className="cp-contact-role">{t(c.role)}</p>
            </div>
          </div>
          <div className="cp-contact-details">
            <div>
              <div className="cp-contact-label">{t('Email')}</div>
              <a className="cp-contact-email" href={`mailto:${c.email}`}>{c.email}</a>
              <p className="cp-contact-tel">{t('Tel: {phone}', { phone: c.phone ?? '-' })}</p>
            </div>
            <a className="cp-contact-btn" href={`mailto:${c.email}`}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="3" y="5" width="18" height="14" rx="2" />
                <path d="m3 7 9 6 9-6" />
              </svg>
              {t('Send email')}
            </a>
          </div>
        </article>
      ))}
    </>
  );
}
