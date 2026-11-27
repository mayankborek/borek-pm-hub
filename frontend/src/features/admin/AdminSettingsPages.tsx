import { Fragment, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { SETTING_COPY, useMyProfile, useNotificationSettings, useSetNotificationSetting, useUpdatePhone } from '@/features/profile/meApi';
import { usePasswordChange } from '@/features/profile/usePasswordChange';
import { initials } from './AdminUi';

type Section = 'profile' | 'security' | 'notifications' | 'preferences';

type Area = 'admin' | 'developer';

const LINKS: Record<Area, [Section, string, string][]> = {
  admin: [
    ['profile', 'My profile', paths.adminProfile],
    ['security', 'Security', paths.adminSecurity],
    ['notifications', 'Notifications', paths.adminNotifications],
    ['preferences', 'Preferences', paths.adminPreferences],
  ],
  developer: [
    ['profile', 'My profile', paths.profile],
    ['security', 'Security', paths.pmSecurity],
    ['notifications', 'Notifications', paths.pmNotifications],
    ['preferences', 'Preferences', paths.pmPreferences],
  ],
};

/** Account settings (settings-*.html): a left menu and one panel. */
export function AdminSettingsPage({ section, area = 'admin' }: { section: Section; area?: Area }) {
  const { t } = usePrefs();
  const body: Record<Section, [string, string, ReactNode]> = {
    profile: ['My profile', 'Your account identity and contact details.', <ProfilePanel area={area} />],
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
          {LINKS[area].map(([id, label, to]) => (
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

function ProfilePanel({ area }: { area: Area }) {
  const { user } = useAuth();
  const { t } = usePrefs();
  const toast = useToast();
  const profile = useMyProfile();
  const updatePhone = useUpdatePhone();
  const phone = profile.data?.phone ?? '';
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  if (!user) return null;

  const save = async () => {
    try {
      await updatePhone.mutateAsync(draft.trim());
      setEditing(false);
      toast.success('Profile updated.');
    } catch (e) {
      toast.error(describeApiError(e, t('That didn’t work. Try again.')));
    }
  };

  return (
    <>
      <div className="bf-profile">
        <span className="bf-av">{initials(user.name)}</span>
        <div>
          <h2>{user.name}</h2>
          <p style={{ marginTop: 12 }}>{t(area === 'admin' ? 'Administrator' : 'Developer')} · Borek Solutions</p>
        </div>
        {editing ? (
          <button type="button" className="bf-btn primary" disabled={updatePhone.isPending} onClick={() => void save()}>{t('Save changes')}</button>
        ) : (
          <button type="button" className="bf-btn primary" disabled={!profile.data} onClick={() => { setDraft(phone); setEditing(true); }}>{t('Edit profile')}</button>
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
  const pw = usePasswordChange();
  if (!user) return null;

  return (
    <>
      <h3 style={{ fontSize: 14, marginTop: 24 }}>{t('Password')}</h3>
      <p className="bf-muted" style={{ marginTop: 8, fontSize: 12 }}>{t('Change your sign-in password. You will sign in again afterwards.')}</p>
      <form
        className="bf-facts"
        style={{ marginTop: 14 }}
        onSubmit={(e) => {
          e.preventDefault();
          void pw.submit();
        }}
      >
        <div>
          <label htmlFor="bf-pw-current">{t('Current password')}</label>
          <input id="bf-pw-current" type="password" autoComplete="current-password" value={pw.current} maxLength={200} onChange={(e) => pw.setCurrent(e.target.value)} />
        </div>
        <div>
          <label htmlFor="bf-pw-new">{t('New password')}</label>
          <input id="bf-pw-new" type="password" autoComplete="new-password" value={pw.next} maxLength={200} onChange={(e) => pw.setNext(e.target.value)} />
        </div>
        <div>
          <label htmlFor="bf-pw-confirm">{t('Confirm new password')}</label>
          <input id="bf-pw-confirm" type="password" autoComplete="new-password" value={pw.confirm} maxLength={200} onChange={(e) => pw.setConfirm(e.target.value)} />
        </div>
        {pw.error && <p className="bf-error" role="alert">{pw.error}</p>}
        <div>
          <button type="submit" className="bf-btn blue" disabled={pw.busy}>{t('Change password')}</button>
        </div>
      </form>
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
    </>
  );
}

function NotificationsPanel() {
  const { t } = usePrefs();
  const toast = useToast();
  const settings = useNotificationSettings();
  const set = useSetNotificationSetting();
  const list = settings.data ?? [];
  return (
    <>
      {settings.isPending && <p className="bf-muted" style={{ marginTop: 24 }}>{t('Loading…')}</p>}
      {settings.isError && (
        <p className="bf-error" role="alert" style={{ marginTop: 24 }}>
          {describeApiError(settings.error, t('We couldn’t load your notification settings'))}{' '}
          <button type="button" className="bf-link" onClick={() => settings.refetch()}>{t('Retry')}</button>
        </p>
      )}
      {!settings.isPending && !settings.isError && !list.length && <p className="bf-muted" style={{ marginTop: 24 }}>{t('There are no notification settings for your role.')}</p>}
      {list.map(({ key, enabled }, i) => {
        const [name, text] = SETTING_COPY[key] ?? [key, ''];
        return (
          <Fragment key={key}>
            {i > 0 && <hr className="bf-rule" />}
            <label className="bf-line" style={{ marginTop: i === 0 ? 24 : 0, minHeight: 48 }}>
              <div><h3 style={{ fontSize: 13 }}>{t(name)}</h3><p>{t(text)}</p></div>
              <input
                type="checkbox"
                className="bf-sw"
                checked={enabled}
                onChange={(e) => set.mutate({ key, enabled: e.target.checked }, { onError: (err) => toast.error(describeApiError(err, t('That didn’t work. Try again.'))) })}
              />
            </label>
          </Fragment>
        );
      })}
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
