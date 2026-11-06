import { useState } from 'react';
import { Navigate, useLocation, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import type { CreatedUser } from './adminApi';
import { Back } from './Back';

/** The server shows an invitation link once, so it travels here in router state and is gone on reload. */
export function AdminInvitationPage() {
  const { t, lang } = usePrefs();
  const { userId = '' } = useParams();
  const created = (useLocation().state as { created?: CreatedUser } | null)?.created;
  const [copied, setCopied] = useState(false);

  if (!created || created.user.id !== userId) return <Navigate to={paths.adminUser(userId)} replace />;

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
    <>
      <Back to={paths.adminUsers} label="Users" />
      <h2 className="ad-title ad-title--lg ad-gap">{t('Share invitation link')}</h2>
      <p className="ad-meta">{t('The account is ready for activation.')}</p>
      <section className="ad-card ad-card--link">
        <h3>{created.user.name}</h3>
        <p className="ad-card-sub">{created.user.email}</p>
        <p className="ad-card-status">{t(created.user.is_active ? 'Pending activation' : 'Inactive')}</p>
        <div className="ad-copy">
          <input className="ad-copy-field" readOnly value={created.invite.url} aria-label={t('Sign-in link')} onFocus={(e) => e.currentTarget.select()} />
          <button type="button" className="ad-btn ad-btn--ghost" onClick={copy}>{t(copied ? 'Copied' : 'Copy')}</button>
        </div>
        <p className="ad-hint">{t('Send this to the person yourself: on mail or on Teams.')}</p>
        <p className="ad-hint">{t('It works once and expires on {date}. It won’t be shown again.', { date: expires })}</p>
      </section>
    </>
  );
}
