import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf } from './format';
import { useProjectContext } from './ClientProjectLayout';

export function ClientContactsPage() {
  const { project } = useProjectContext();
  const { t } = usePrefs();

  return (
    <>
      <h2 className="cp-section-title">{t('Project contacts')}</h2>
      <p className="cp-section-sub">{t('Contact your Project Manager for delivery questions and shared updates.')}</p>
      {project.contacts.map((c) => (
        <article className="cp-contact" key={c.email}>
          <div className="cp-contact-head">
            <span className="cp-contact-initials" aria-hidden="true">{initialsOf(c.name)}</span>
            <h3 className="cp-contact-name">{c.name}</h3>
            <span className="cp-contact-role">{t(c.role)}</span>
          </div>
          <a className="cp-contact-email" href={`mailto:${c.email}`}>{c.email}</a>
          <p className="cp-contact-tel">{t('Tel: {phone}', { phone: c.phone ?? '-' })}</p>
        </article>
      ))}
    </>
  );
}
