import { useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { useNewInvite, type CreatedUser } from './adminApi';
import { profileActions, topicActions, usePhone, useTopic } from './adminStore';
import { ShareLinkModal, initials } from './AdminUi';

type Section = 'profile' | 'security' | 'notifications' | 'preferences';

const LINKS: [Section, string, string][] = [
  ['profile', 'My profile', paths.adminProfile],
  ['security', 'Security', paths.adminSecurity],
  ['notifications', 'Notifications', paths.adminNotifications],
  ['preferences', 'Preferences', paths.adminPreferences],
];

/** Account settings (settings-*.html): a left menu and one panel. */
export function AdminSettingsPage({ section }: { section: Section }) {
  const { t } = usePrefs();
  const body: Record<Section, [string, string, ReactNode]> = {
    profile: ['My profile', 'Your account identity and contact details.', <ProfilePanel />],
    security: ['Security', 'Manage your password and current session.', <SecurityPanel />],
    notifications: ['Notifications', 'Choose which project updates you receive.', <NotificationsPanel />],
    preferences: ['Preferences', 'Set the language and appearance for your account.', <PreferencesPanel />],
  };
  const [title, sub, panel] = body[section];
  return (
    <main className="bf-settings">
      <h1>{t('Account settings')}</h1>
      <p className="bf-sub">{t('Manage your profile and portal preferences')}</p>
      <div className="bf-cols">
        <nav aria-label={t('Settings')}>
          <h6>{t('Settings')}</h6>
          {LINKS.map(([id, label, to]) => (
            <Link key={id} to={to} className={id === section ? 'on' : undefined} aria-current={id === section ? 'page' : undefined}>{t(label)}</Link>
          ))}
        </nav>
        <section className="bf-card bf-box">
          <h2>{t(title)}</h2>
          <p className="bf-muted">{t(sub)}</p>
          {panel}
        </section>
      </div>
    </main>
  );
}

function ProfilePanel() {
  const { user } = useAuth();
  const { t } = usePrefs();
  const toast = useToast();
  const phone = usePhone();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  if (!user) return null;

  return (
    <>
      <div className="bf-profile">
        <span className="bf-av">{initials(user.name)}</span>
        <div>
          <h2>{user.name}</h2>
          <p style={{ marginTop: 12 }}>{t('Administrator')} · Borek Solutions</p>
        </div>
        {editing ? (
          <button type="button" className="bf-btn primary" onClick={() => { profileActions.setPhone(draft.trim()); setEditing(false); toast.success('Profile updated.'); }}>{t('Save changes')}</button>
        ) : (
          <button type="button" className="bf-btn primary" onClick={() => { setDraft(phone); setEditing(true); }}>{t('Edit profile')}</button>
        )}
      </div>
      <h3>{t('Contact details')}</h3>
      <div className="bf-facts">
        <div>{t('Email address')}<b>{user.email}</b></div>
        <div>{t('Workspace · Read only')}<b>Borek Solutions</b></div>
        <div>
          <label htmlFor="bf-phone">{t('Phone number')}</label>
          {editing ? <input id="bf-phone" type="tel" autoComplete="tel" value={draft} maxLength={40} onChange={(e) => setDraft(e.target.value)} /> : <b>{phone || t('Not set')}</b>}
        </div>
      </div>
    </>
  );
}

function SecurityPanel() {
  const { user, signOut } = useAuth();
  const { t } = usePrefs();
  const navigate = useNavigate();
  const toast = useToast();
  const newInvite = useNewInvite();
  const [link, setLink] = useState<CreatedUser | null>(null);
  if (!user) return null;

  const reset = async () => {
    try {
      setLink(await newInvite.mutateAsync(user.id));
    } catch (e) {
      toast.error(describeApiError(e, t('That didn’t work. Try again.')));
    }
  };

  return (
    <>
      <h3 style={{ fontSize: 14, marginTop: 24 }}>{t('Password')}</h3>
      <p className="bf-muted" style={{ marginTop: 8, fontSize: 12 }}>{t('Start a secure password reset for your account.')}</p>
      <div className="bf-line" style={{ background: 'var(--bf-bg)', borderRadius: 8, padding: '12px 14px', marginTop: 14 }}>
        <div><b>{t('Password')}</b><p>{t('Reset your sign-in password.')}</p></div>
        <button type="button" className="bf-btn blue" disabled={newInvite.isPending} onClick={reset}>{t('Reset password')}</button>
      </div>
      <hr className="bf-rule" />
      <div className="bf-line">
        <div>
          <h3 style={{ fontSize: 14 }}>{t('Current session')}</h3>
          <p>{t('End your current Borek Flow session on this device.')}</p>
        </div>
        <button type="button" style={{ color: 'var(--bf-blue)', fontWeight: 600, marginRight: 54, background: 'none', border: 0 }} onClick={() => void signOut().then(() => navigate(paths.login, { replace: true }))}>
          {t('Log out')}
        </button>
      </div>
      {link && <ShareLinkModal name={link.user.name} email={link.user.email} url={link.invite.url} expiresAt={link.invite.expires_at} onClose={() => setLink(null)} />}
    </>
  );
}

const TOPICS: [string, string, string][] = [
  ['reports', 'Project reports', 'New status reports shared by your project manager.'],
  ['milestones', 'Milestones', 'Changes to milestone dates and completion.'],
  ['change-requests', 'Change requests', 'Updates on requests you submitted.'],
];

function NotificationsPanel() {
  return (
    <>
      {TOPICS.map(([id, name, text], i) => (
        <Topic key={id} id={id} name={name} text={text} first={i === 0} />
      ))}
    </>
  );
}

function Topic({ id, name, text, first }: { id: string; name: string; text: string; first: boolean }) {
  const { t } = usePrefs();
  const on = useTopic(id);
  return (
    <>
      {!first && <hr className="bf-rule" />}
      <label className="bf-line" style={{ marginTop: first ? 24 : 0, minHeight: 48 }}>
        <div><h3 style={{ fontSize: 13 }}>{t(name)}</h3><p>{t(text)}</p></div>
        <input type="checkbox" className="bf-sw" checked={on} onChange={(e) => topicActions.set(id, e.target.checked)} />
      </label>
    </>
  );
}

function PreferencesPanel() {
  const { lang, setLang, theme, setTheme, t } = usePrefs();
  return (
    <>
      <h3 style={{ fontSize: 13, marginTop: 26 }}>{t('Preferred language')}</h3>
      <p className="bf-muted" style={{ fontSize: 12, margin: '7px 0 4px' }}>{t('Used throughout your Borek Flow workspace.')}</p>
      <label className="bf-field" style={{ width: 370, display: 'block' }}>
        <select aria-label={t('Preferred language')} value={lang} onChange={(e) => setLang(e.target.value as 'en' | 'de')}>
          <option value="en">English (EN)</option>
          <option value="de">Deutsch (DE)</option>
        </select>
      </label>
      <hr className="bf-rule" />
      <h3 style={{ fontSize: 13 }}>{t('Appearance')}</h3>
      <p className="bf-muted" style={{ fontSize: 12, marginTop: 7 }}>{t('Choose light or dark theme.')}</p>
      <label className="bf-line" style={{ background: 'var(--bf-bg)', borderRadius: 8, padding: '16px 14px', marginTop: 16 }}>
        <b style={{ fontSize: 12 }}>{t('Dark theme')}</b>
        <input type="checkbox" className="bf-sw" checked={theme === 'dark'} onChange={(e) => setTheme(e.target.checked ? 'dark' : 'light')} />
      </label>
    </>
  );
}
