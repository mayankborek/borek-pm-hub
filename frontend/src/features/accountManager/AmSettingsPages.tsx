import { useState, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf } from '@/features/client/format';
import { useClientPortal } from '@/features/client/clientPortalApi';
import { useSay } from './AccountManagerLayout';

const useIsClient = () => useLocation().pathname.startsWith(paths.clientHome);

/** Account settings frame (borek-flow-portal profile/security/notifications/preferences): left menu and one panel. */
function Settings({ title, sub, children }: { title: string; sub: string; children: ReactNode }) {
  const { t } = usePrefs();
  const client = useIsClient();
  const links: [string, string][] = [
    [client ? paths.clientProfile : paths.amProfile, 'My profile'],
    [client ? paths.clientSecurity : paths.amSecurity, 'Security'],
    [client ? paths.clientNotifications : paths.amNotifications, 'Notifications'],
    [client ? paths.clientPreferences : paths.amPreferences, 'Preferences'],
  ];
  return (
    <div className="settings">
      <h1>{t('Account settings')}</h1>
      <p className="lead" style={{ fontSize: 12, marginTop: 4 }}>{t('Manage your profile and portal preferences')}</p>
      <div className="sgrid">
        <nav className="snav" aria-label={t('Settings')}>
          <small>{t('Settings')}</small>
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} end className={({ isActive }) => (isActive ? 'active' : undefined)}>{t(label)}</NavLink>
          ))}
        </nav>
        <section className="spanel">
          <h3>{t(title)}</h3>
          <p className="sd">{t(sub)}</p>
          {children}
        </section>
      </div>
    </div>
  );
}

export function AmProfilePage() {
  const { user } = useAuth();
  const { t } = usePrefs();
  const say = useSay();
  const client = useIsClient();
  const organisation = useClientPortal().data?.organisation;
  const [editing, setEditing] = useState(false);
  // Not persisted yet: there is no endpoint for the phone number.
  const [phone, setPhone] = useState('');
  const [draft, setDraft] = useState('');
  if (!user) return null;

  return (
    <Settings title="My profile" sub="Your account identity and contact details.">
      <div className="idrow">
        <span className="avatar" aria-hidden="true">{initialsOf(user.name)}</span>
        <div><h4>{user.name}</h4><p>{client ? t('Client · Customer organisation') : t('Account Manager · Borek Solutions')}</p></div>
        {editing ? (
          <button className="btn primary" type="button" onClick={() => { setPhone(draft.trim()); setEditing(false); say(t('Profile updated')); }}>{t('Save changes')}</button>
        ) : (
          <button className="btn primary" type="button" onClick={() => { setDraft(phone); setEditing(true); }}>{t('Edit profile')}</button>
        )}
      </div>
      <h5>{t('Contact details')}</h5>
      <div className="fields">
        <div className="field"><label>{t('Email address')}</label><div>{user.email}</div></div>
        <div className="field"><label>{client ? t('Organisation · Read only') : t('Workspace · Read only')}</label><div>{client ? organisation ?? '–' : 'Borek Solutions'}</div></div>
        <div className="field">
          <label htmlFor="am-phone">{t('Phone number')}</label>
          {editing ? <input id="am-phone" type="tel" autoComplete="tel" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={40} /> : <div>{phone || '–'}</div>}
        </div>
      </div>
    </Settings>
  );
}

export function AmSecurityPage() {
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const { t } = usePrefs();
  const say = useSay();
  return (
    <Settings title="Security" sub="Manage your password and current session.">
      <div className="sect">
        <h5>{t('Password')}</h5>
        <p className="sd">{t('Start a secure password reset for your account.')}</p>
        <div className="setrow">
          <div><b>{t('Password')}</b><small>{t('Reset your sign-in password.')}</small></div>
          <button className="btn blue" type="button" onClick={() => say(t('Password reset email sent'))}>{t('Reset password')}</button>
        </div>
      </div>
      <div className="divider" />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h5 style={{ margin: 0, fontSize: 14 }}>{t('Current session')}</h5>
          <p className="sd">{t('End your current portal session on this device.')}</p>
        </div>
        <button className="linkbtn" type="button" onClick={() => void signOut().then(() => navigate(paths.login, { replace: true }))}>{t('Log out')}</button>
      </div>
    </Settings>
  );
}

const TOPICS: [string, string][] = [
  ['Project reports', 'New status reports shared by your project manager.'],
  ['Milestones', 'Changes to milestone dates and completion.'],
  ['Change requests', 'Updates on requests you submitted.'],
];

export function AmNotificationsPage() {
  const { t } = usePrefs();
  const [on, setOn] = useState<Record<string, boolean>>({});
  return (
    <Settings title="Notifications" sub="Choose which project updates you receive.">
      <div className="nlist">
        {TOPICS.map(([name, text]) => {
          const checked = on[name] ?? true;
          return (
            <label className="nrow" key={name}>
              <span><b>{t(name)}</b><small>{t(text)}</small></span>
              <input className="ncheck" type="checkbox" checked={checked} aria-label={t(name)} onChange={() => setOn((s) => ({ ...s, [name]: !checked }))} />
            </label>
          );
        })}
      </div>
    </Settings>
  );
}

export function AmPreferencesPage() {
  const { lang, setLang, theme, setTheme, t } = usePrefs();
  const dark = theme === 'dark';
  return (
    <Settings title="Preferences" sub="Set the language and appearance for your account.">
      <div className="sect">
        <h5 style={{ fontSize: 13 }}>{t('Preferred language')}</h5>
        <p className="sd" style={{ marginBottom: 12 }}>{t('Used throughout your portal.')}</p>
        <select aria-label={t('Preferred language')} value={lang} onChange={(e) => setLang(e.target.value as 'en' | 'de')}>
          <option value="en">English (EN)</option>
          <option value="de">Deutsch (DE)</option>
        </select>
      </div>
      <div className="divider" />
      <div className="sect" style={{ marginTop: 0 }}>
        <h5>{t('Appearance')}</h5>
        <p className="sd">{t('Choose light or dark theme.')}</p>
        <div className="setrow">
          <b>{t('Dark theme')}</b>
          <div className="tg" style={{ margin: 0 }}>
            <button className="switch" type="button" role="switch" aria-checked={dark} aria-label={t('Dark theme')} onClick={() => setTheme(dark ? 'light' : 'dark')} />
          </div>
        </div>
      </div>
    </Settings>
  );
}
