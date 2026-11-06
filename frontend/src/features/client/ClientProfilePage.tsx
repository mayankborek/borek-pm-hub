import { useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { initialsOf } from './format';
import './clientPortal.css';

const chevron = (
  <svg viewBox="0 0 12 8" fill="none" aria-hidden="true">
    <path d="M1 1l5 5 5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

/** Client profile (borek-flow-auth/profile.html): name and email are managed by Borek, only the phone number is editable. */
export function ClientProfilePage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const { lang, setLang, theme, setTheme, t } = usePrefs();
  const [editing, setEditing] = useState(false);
  // Not persisted yet: there is no endpoint for the client's phone number.
  const [saved, setSaved] = useState('');
  const [phone, setPhone] = useState('');
  const discardRef = useRef<HTMLDialogElement>(null);
  const orgRef = useRef<HTMLDialogElement>(null);
  const langRef = useRef<HTMLDialogElement>(null);
  const phoneRef = useRef<HTMLInputElement>(null);
  if (!user) return null;

  const [firstName, ...rest] = user.name.split(' ');
  const dark = theme === 'dark';

  const startEdit = () => {
    setPhone(saved);
    setEditing(true);
    setTimeout(() => phoneRef.current?.focus());
  };
  const cancel = () => {
    if (phone !== saved) discardRef.current?.showModal();
    else setEditing(false);
  };
  const discard = () => {
    discardRef.current?.close();
    setPhone(saved);
    setEditing(false);
  };
  const save = (e: FormEvent) => {
    e.preventDefault();
    setSaved(phone.trim());
    setPhone(phone.trim());
    setEditing(false);
  };
  // Closing on a click of the backdrop (the dialog element itself, not its content).
  const backdropClose = (e: React.MouseEvent<HTMLDialogElement>) => {
    if (e.target === e.currentTarget) e.currentTarget.close();
  };

  return (
    <>
      <div className="cp-profile">
        <p className="cp-profile-sub">{t('Manage your personal details and account preferences.')}</p>

        <form className={editing ? 'cp-profile-form cp-edit' : 'cp-profile-form'} onSubmit={save} noValidate>
          <section className="cp-pcard cp-pcard-head" aria-label={t('Profile summary')}>
            <span className="cp-avatar" aria-hidden="true">{initialsOf(user.name)}</span>
            <div className="cp-who">
              <p className="cp-who-name">{user.name}</p>
              <p className="cp-who-role">{t('Client · Customer organisation')}</p>
            </div>
            {editing ? (
              <div className="cp-pactions">
                <button className="cp-pbtn" type="button" onClick={cancel}>{t('Cancel')}</button>
                <button className="cp-pbtn cp-primary" type="submit">{t('Save Changes')}</button>
              </div>
            ) : (
              <button className="cp-pbtn cp-primary" type="button" onClick={startEdit}>{t('Edit profile')}</button>
            )}
          </section>

          <section className="cp-pcard" aria-labelledby="cp-personal-title">
            <h2 className="cp-pcard-title" id="cp-personal-title">{t('Personal & contact information')}</h2>
            <p className="cp-pcard-sub">{t('Your contact details for collaborators.')}</p>
            <div className="cp-pgrid">
              <div className="cp-pfield cp-ro">
                <label className="cp-pfield-label" htmlFor="cp-first-name">{t('First name')}</label>
                <input className="cp-pfield-input" id="cp-first-name" value={firstName} readOnly />
              </div>
              <div className="cp-pfield cp-ro">
                <label className="cp-pfield-label" htmlFor="cp-last-name">{t('Last name')}</label>
                <input className="cp-pfield-input" id="cp-last-name" value={rest.join(' ')} readOnly />
              </div>
              <div className="cp-pfield cp-ro">
                <label className="cp-pfield-label" htmlFor="cp-work-email">{t('Work email')}</label>
                <input className="cp-pfield-input" id="cp-work-email" type="email" value={user.email} readOnly />
              </div>
              <div className="cp-pfield cp-phone">
                <label className="cp-pfield-label" htmlFor="cp-phone">{t('Phone number')}</label>
                <input
                  ref={phoneRef}
                  className="cp-pfield-input"
                  id="cp-phone"
                  type="tel"
                  autoComplete="tel"
                  value={editing ? phone : saved || '–'}
                  readOnly={!editing}
                  onChange={(e) => setPhone(e.target.value)}
                />
              </div>
            </div>
          </section>

          <div className="cp-pcols">
            <section className="cp-pcard" aria-labelledby="cp-prefs-title">
              <h2 className="cp-pcard-title" id="cp-prefs-title">{t('Preferences')}</h2>
              <div className="cp-pfield" style={{ marginTop: 13 }}>
                <span className="cp-pfield-label" id="cp-lang-label">{t('Language')}</span>
                <button
                  className="cp-select-btn"
                  type="button"
                  aria-labelledby="cp-lang-label cp-lang-value"
                  aria-haspopup="dialog"
                  onClick={() => langRef.current?.showModal()}
                >
                  <span id="cp-lang-value">{lang === 'de' ? 'Deutsch (DE)' : 'English (EN)'}</span>
                  {chevron}
                </button>
              </div>
              <div className="cp-theme">
                <span className="cp-pfield-label">{t('Theme')}</span>
                <div className="cp-theme-row">
                  <span id="cp-theme-value">{dark ? t('Dark mode') : t('Light mode')}</span>
                  <button
                    className="cp-toggle"
                    type="button"
                    role="switch"
                    aria-checked={dark}
                    aria-labelledby="cp-theme-value"
                    onClick={() => setTheme(dark ? 'light' : 'dark')}
                  />
                </div>
              </div>
            </section>

            <section className="cp-pcard" aria-labelledby="cp-account-title">
              <h2 className="cp-pcard-title" id="cp-account-title">{t('Account & security')}</h2>
              <p className="cp-pcard-sub">{t('Manage access to your Borek account.')}</p>
              <div className="cp-arow">
                <span>{t('Organisation sign-in')}</span>
                <button className="cp-text-btn" type="button" onClick={() => orgRef.current?.showModal()}>{t('Details')}</button>
              </div>
              <button
                className="cp-text-btn cp-signout"
                type="button"
                onClick={() => void signOut().then(() => navigate(paths.clientLogin, { replace: true }))}
              >
                {t('Sign out')}
              </button>
            </section>
          </div>
        </form>
      </div>

      <dialog className="cp-dialog" ref={discardRef} aria-labelledby="cp-discard-title" onClick={backdropClose}>
        <div className="cp-dialog-inner">
          <h2 className="cp-dialog-title" id="cp-discard-title">{t('Discard profile changes?')}</h2>
          <p className="cp-dialog-text">{t('Your unsaved changes will be lost.')}</p>
          <div className="cp-dialog-row">
            <button className="cp-dbtn" type="button" autoFocus onClick={() => discardRef.current?.close()}>{t('Keep editing')}</button>
            <button className="cp-dbtn" type="button" onClick={discard}>{t('Discard changes')}</button>
          </div>
        </div>
      </dialog>

      <dialog className="cp-dialog" ref={orgRef} aria-labelledby="cp-org-title" onClick={backdropClose}>
        <div className="cp-dialog-inner">
          <h2 className="cp-dialog-title" id="cp-org-title">{t('Organisation sign-in')}</h2>
          <p className="cp-dialog-text">
            {t('Your organisation manages sign-in and identity verification. Contact your organisation administrator for changes to authentication.')}
          </p>
          <button className="cp-dbtn" type="button" onClick={() => orgRef.current?.close()}>{t('Close')}</button>
        </div>
      </dialog>

      <dialog className="cp-dialog" ref={langRef} aria-labelledby="cp-language-title" style={{ width: 400 }} onClick={backdropClose}>
        <div className="cp-dialog-inner">
          <h2 className="cp-dialog-title" id="cp-language-title">{t('Preferred language')}</h2>
          <div className="cp-dialog-stack">
            {([['en', 'English (EN)'], ['de', 'Deutsch (DE)']] as const).map(([code, label]) => (
              <button
                key={code}
                className="cp-dbtn"
                type="button"
                aria-pressed={lang === code}
                onClick={() => {
                  setLang(code);
                  langRef.current?.close();
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </dialog>
    </>
  );
}
