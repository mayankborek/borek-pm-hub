import { useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf } from '@/features/client/format';
import { describeApiError } from '@/shared/api/client';
import { SETTING_COPY, useMyProfile, useNotificationSettings, useSetNotificationSetting, useUpdatePhone } from '@/features/profile/meApi';
import { usePasswordChange } from '@/features/profile/usePasswordChange';
import { useClientPortal } from '@/features/client/clientPortalApi';
import { Toast, useSay } from './AccountManagerLayout';
import './am.css';
import '@/features/client/clientPortal.css';
import '@/features/client/slateRounded.css';

const useIsClient = () => useLocation().pathname.startsWith(paths.clientHome);
const useIsManager = () => useLocation().pathname.startsWith(paths.managerHome);
const useIsPm = () => useLocation().pathname.startsWith(paths.profile);

/** The Project Manager's account settings reuse these pages inside the staff shell, so they bring their own `.am` scope and toast. */
export function PmSettings({ children }: { children: ReactNode }) {
  return (
    <div className="am am-slate am-client" style={{ minHeight: 0, background: 'none' }}>
      <Toast>{children}</Toast>
    </div>
  );
}

/** Account settings frame (borek-flow-portal profile/security/notifications/preferences): left menu and one panel. */
function Settings({ title, sub, children }: { title: string; sub: string; children: ReactNode }) {
  const { t } = usePrefs();
  const client = useIsClient();
  const manager = useIsManager();
  const pm = useIsPm();
  const pick = (c: string, m: string, a: string, p: string) => (client ? c : manager ? m : pm ? p : a);
  const links: [string, string][] = [
    [pick(paths.clientProfile, paths.managerProfile, paths.amProfile, paths.profile), 'My profile'],
    [pick(paths.clientSecurity, paths.managerSecurity, paths.amSecurity, paths.pmSecurity), 'Security'],
    [pick(paths.clientNotifications, paths.managerNotifications, paths.amNotifications, paths.pmNotifications), 'Notifications'],
    [pick(paths.clientPreferences, paths.managerPreferences, paths.amPreferences, paths.pmPreferences), 'Preferences'],
  ];
  return (
    <div className="settings">
      <h1>{t('Account settings')}</h1>
      <p className="lead" style={{ fontSize: 'var(--fs-12)', marginTop: 4 }}>{t('Manage your profile and portal preferences')}</p>
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
  const manager = useIsManager();
  const pm = useIsPm();
  const organisation = useClientPortal().data?.organisation;
  const [editing, setEditing] = useState(false);
  const profile = useMyProfile();
  const updatePhone = useUpdatePhone();
  const phone = profile.data?.phone ?? '';
  const [draft, setDraft] = useState('');
  if (!user) return null;

  const save = async () => {
    try {
      await updatePhone.mutateAsync(draft.trim());
      setEditing(false);
      say(t('Profile updated'));
    } catch (e) {
      say(describeApiError(e, t('That didn’t work. Try again.')));
    }
  };

  return (
    <Settings title="My profile" sub="Your account identity and contact details.">
      <div className="idrow">
        <span className="avatar" aria-hidden="true">{initialsOf(user.name)}</span>
        <div><h4>{user.name}</h4><p>{client ? t('Client · Customer organisation') : manager ? t('Manager · Borek Solutions') : pm ? t('Project Manager · Borek Solutions') : t('Account Manager · Borek Solutions')}</p></div>
        {editing ? (
          <button className="btn primary" type="button" disabled={updatePhone.isPending} onClick={() => void save()}>{t('Save changes')}</button>
        ) : (
          <button className="btn primary" type="button" disabled={!profile.data} onClick={() => { setDraft(phone); setEditing(true); }}>{t('Edit profile')}</button>
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
  const { signOut, user } = useAuth();
  const navigate = useNavigate();
  const { t } = usePrefs();
  const pw = usePasswordChange();
  return (
    <Settings title="Security" sub="Manage your password and current session.">
      <div className="sect">
        <h5>{t('Password')}</h5>
        <p className="sd">{t('Change your sign-in password. You will sign in again afterwards.')}</p>
        <form
          className="fields"
          style={{ marginTop: 14 }}
          onSubmit={(e) => {
            e.preventDefault();
            void pw.submit();
          }}
        >
          <div className="field">
            <label htmlFor="am-pw-current">{t('Current password')}</label>
            <input id="am-pw-current" type="password" autoComplete="current-password" value={pw.current} maxLength={200} onChange={(e) => pw.setCurrent(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="am-pw-new">{t('New password')}</label>
            <input id="am-pw-new" type="password" autoComplete="new-password" value={pw.next} maxLength={200} onChange={(e) => pw.setNext(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="am-pw-confirm">{t('Confirm new password')}</label>
            <input id="am-pw-confirm" type="password" autoComplete="new-password" value={pw.confirm} maxLength={200} onChange={(e) => pw.setConfirm(e.target.value)} />
          </div>
          {pw.error && <p role="alert" style={{ gridColumn: '1 / -1', color: 'var(--red, #b42318)', fontSize: 'var(--fs-12)' }}>{pw.error}</p>}
          <div style={{ gridColumn: '1 / -1' }}>
            <button className="btn blue" type="submit" disabled={pw.busy}>{t('Change password')}</button>
          </div>
        </form>
      </div>
      <div className="divider" />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
        <div>
          <h5 style={{ margin: 0, fontSize: 'var(--fs-14)' }}>{t('Forgot your current password?')}</h5>
          <p className="sd">{t('Start a secure password reset for your account. We email you a one-time link.')}</p>
        </div>
        <Link className="btn primary" to={paths.forgotPassword} state={{ email: user?.email }}>{t('Reset password')}</Link>
      </div>
      <div className="divider" />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h5 style={{ margin: 0, fontSize: 'var(--fs-14)' }}>{t('Current session')}</h5>
          <p className="sd">{t('End your current portal session on this device.')}</p>
        </div>
        <button className="linkbtn" type="button" onClick={() => void signOut().then(() => navigate(paths.login, { replace: true }))}>{t('Log out')}</button>
      </div>
    </Settings>
  );
}

export function AmNotificationsPage() {
  const { t } = usePrefs();
  const say = useSay();
  const settings = useNotificationSettings();
  const set = useSetNotificationSetting();
  return (
    <Settings title="Notifications" sub="Choose which project updates you receive.">
      {settings.isPending && <p className="sd">{t('Loading…')}</p>}
      {settings.isError && (
        <p className="sd" role="alert">
          {describeApiError(settings.error, t('We couldn’t load your notification settings'))}{' '}
          <button className="linkbtn" type="button" onClick={() => settings.refetch()}>{t('Retry')}</button>
        </p>
      )}
      <div className="nset">
        {(settings.data ?? []).map(({ key, enabled }) => {
          const [name, text] = SETTING_COPY[key] ?? [key, ''];
          return (
            <div className="setting" key={key}>
              <div>
                <h4 className="setting-name">{t(name)}</h4>
                <p className="setting-desc">{t(text)}</p>
              </div>
              <div className="setting-control">
                <span className="setting-state">{enabled ? t('On') : t('Off')}</span>
                <button
                  className="switch"
                  type="button"
                  role="switch"
                  aria-checked={enabled}
                  aria-label={t(name)}
                  onClick={() => set.mutate({ key, enabled: !enabled }, { onError: (e) => say(describeApiError(e, t('That didn’t work. Try again.'))) })}
                />
              </div>
            </div>
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
        <h5 style={{ fontSize: 'var(--fs-13)' }}>{t('Preferred language')}</h5>
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
