import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import chevronIcon from './assets/chevron-down.svg';
import themeSwitchLight from './assets/theme-switch-light.svg';
import themeSwitchDark from './assets/theme-switch-dark.svg';
import './profile.css';

type Mode = 'view' | 'edit' | 'saved';

export function ProfilePage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<Mode>('view');
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [phone, setPhone] = useState('');
  const [draftPhone, setDraftPhone] = useState('');
  const { lang, setLang, theme, setTheme, t } = usePrefs();
  const dark = theme === 'dark';
  const keepEditingRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!confirmDiscard) return;
    keepEditingRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setConfirmDiscard(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [confirmDiscard]);

  if (!user) return null;

  const [firstName, ...rest] = user.name.split(' ');
  const lastName = rest.join(' ');
  const initials = user.name
    .split(' ')
    .map((p) => p.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase();
  const roleLabel = t(user.role === 'pm' ? 'Project Manager' : 'Developer');

  const save = (e?: React.FormEvent) => {
    e?.preventDefault();
    setPhone(draftPhone.trim());
    setMode('saved');
  };
  const cancel = () => {
    if (draftPhone.trim() !== phone) setConfirmDiscard(true);
    else setMode('view');
  };
  const discard = () => {
    setConfirmDiscard(false);
    setMode('view');
  };

  return (
    <div className="pf">
      <section className="pf-card pf-identity">
        <div className="pf-avatar">
          <span aria-hidden="true">{initials}</span>
        </div>
        <div className="pf-who">
          <h2>{user.name}</h2>
          <p>{roleLabel}</p>
        </div>
      </section>

      <div className="pf-layout">
        <div className="pf-primary">
          {mode === 'view' ? (
            <section className="pf-card">
              <h3>{t('Personal & contact information')}</h3>
              <p className="pf-desc">{t('Your contact details for collaborators.')}</p>
              <div className="pf-row">
                <div className="pf-field">
                  <span className="pf-label">{t('First name')}</span>
                  <span className="pf-value">{firstName}</span>
                </div>
                <div className="pf-field">
                  <span className="pf-label">{t('Last name')}</span>
                  <span className="pf-value">{lastName || '—'}</span>
                </div>
              </div>
              <div className="pf-row">
                <div className="pf-field">
                  <span className="pf-label">{t('Work email')}</span>
                  <span className="pf-value">{user.email}</span>
                </div>
                <div className="pf-field">
                  <span className="pf-label">{t('Phone number')}</span>
                  <span className="pf-value">{phone || '—'}</span>
                </div>
              </div>
            </section>
          ) : (
            <form className="pf-card" id="profile-form" onSubmit={save} noValidate>
              <h3>{t('Personal & contact information')}</h3>
              <p className="pf-desc">{t('Name and work email are managed by Borek. Phone number is optional.')}</p>
              <div className="pf-row">
                <div className="pf-field">
                  <label className="pf-label" htmlFor="pf-fn">{t('First name')}</label>
                  <input id="pf-fn" value={firstName} readOnly />
                </div>
                <div className="pf-field">
                  <label className="pf-label" htmlFor="pf-ln">{t('Last name')}</label>
                  <input id="pf-ln" value={lastName} readOnly />
                </div>
              </div>
              <div className="pf-row">
                <div className="pf-field">
                  <label className="pf-label" htmlFor="pf-em">{t('Work email')}</label>
                  <input id="pf-em" type="email" value={user.email} readOnly />
                </div>
                <div className="pf-field">
                  <label className="pf-label" htmlFor="pf-ph">{t('Phone number (optional)')}</label>
                  <input
                    id="pf-ph"
                    type="tel"
                    autoComplete="tel"
                    value={mode === 'saved' ? phone : draftPhone}
                    readOnly={mode === 'saved'}
                    onChange={(e) => setDraftPhone(e.target.value)}
                  />
                </div>
              </div>
            </form>
          )}

          {mode !== 'view' && <div className="pf-actions">
            {mode === 'edit' && (
              <>
                <button type="button" className="pf-btn" onClick={cancel}>{t('Cancel')}</button>
                <button type="submit" form="profile-form" className="pf-btn primary">{t('Save changes')}</button>
              </>
            )}
            {mode === 'saved' && (
              <>
                <span className="pf-saved" role="status">{t('Changes saved just now')}</span>
                <button type="button" className="pf-btn primary" onClick={() => setMode('view')}>{t('Done')}</button>
              </>
            )}
          </div>}
        </div>

        <aside className="pf-secondary">
          <section className="pf-card">
            <h3>{t('Preferences')}</h3>
            <div className="pf-pref">
              <label className="pf-label" htmlFor="pf-lang">{t('Language')}</label>
              <div className="pf-select">
                <select id="pf-lang" value={lang} onChange={(e) => setLang(e.target.value === 'de' ? 'de' : 'en')}>
                  <option value="en">{t('English (EN)')}</option>
                  <option value="de">Deutsch (DE)</option>
                </select>
                <img src={chevronIcon} alt="" />
              </div>
            </div>
            <div className="pf-pref">
              <span className="pf-label">{t('Theme')}</span>
              <div className="pf-toggle-row">
                <div>
                  <strong>{t('Dark mode')}</strong>
                </div>
                <button
                  type="button"
                  className="pf-toggle"
                  role="switch"
                  aria-checked={dark}
                  aria-label={t('Dark mode')}
                  onClick={() => setTheme(dark ? 'light' : 'dark')}
                >
                  <img src={dark ? themeSwitchDark : themeSwitchLight} alt="" />
                </button>
              </div>
            </div>
          </section>

          <section className="pf-card">
            <h3>{t('Account & security')}</h3>
            <p className="pf-desc">{t('Manage access to your Borek account.')}</p>
            <div className="pf-setting">
              <div>
                <strong>{t('Password')}</strong>
              </div>
              <button type="button" className="pf-link">{t('Change')}</button>
            </div>
            <div className="pf-account">
              <button
                type="button"
                className="pf-link"
                onClick={async () => {
                  await signOut();
                  navigate(paths.login, { replace: true });
                }}
              >
                {t('Sign out')}
              </button>
            </div>
          </section>
        </aside>
      </div>

      {confirmDiscard && (
        <div className="pf-overlay" role="dialog" aria-modal="true" aria-labelledby="pf-dlg-title" aria-describedby="pf-dlg-msg">
          <div className="pf-dialog">
            <h2 id="pf-dlg-title">{t('Discard unsaved changes?')}</h2>
            <p id="pf-dlg-msg">{t('Your profile changes haven’t been saved. You can keep editing or discard them.')}</p>
            <div className="pf-actions">
              <button ref={keepEditingRef} type="button" className="pf-btn" onClick={() => setConfirmDiscard(false)}>
                {t('Keep editing')}
              </button>
              <button type="button" className="pf-btn primary" onClick={discard}>{t('Discard changes')}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
