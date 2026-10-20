import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';
import avatarImg from './assets/avatar.png';
import chevronIcon from './assets/chevron-down.svg';
import toggleOffIcon from './assets/toggle-off.svg';
import './profile.css';

type Mode = 'view' | 'edit' | 'saved';

export function ProfilePage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<Mode>('view');
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [phone, setPhone] = useState('');
  const [draftPhone, setDraftPhone] = useState('');
  const [language, setLanguage] = useState('en');
  const [dark, setDark] = useState(false);
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
  const roleLabel = user.role === 'pm' ? 'Project Manager' : 'Developer';
  const editing = mode !== 'view';

  const startEdit = () => {
    setDraftPhone(phone);
    setMode('edit');
  };
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
          {editing ? <img src={avatarImg} alt={user.name} /> : <span aria-hidden="true">{initials}</span>}
        </div>
        <div className="pf-who">
          <h2>{user.name}</h2>
          <p>{roleLabel}</p>
        </div>
        {editing ? (
          <button type="button" className="pf-btn">
            Change photo
          </button>
        ) : (
          <button type="button" className="pf-btn primary" onClick={startEdit}>
            Edit profile
          </button>
        )}
      </section>

      <div className="pf-layout">
        <div className="pf-primary">
          {mode === 'view' ? (
            <section className="pf-card">
              <h3>Personal &amp; contact information</h3>
              <p className="pf-desc">Your contact details for collaborators.</p>
              <div className="pf-row">
                <div className="pf-field">
                  <span className="pf-label">First name</span>
                  <span className="pf-value">{firstName}</span>
                </div>
                <div className="pf-field">
                  <span className="pf-label">Last name</span>
                  <span className="pf-value">{lastName || '—'}</span>
                </div>
              </div>
              <div className="pf-row">
                <div className="pf-field">
                  <span className="pf-label">Work email</span>
                  <span className="pf-value">{user.email}</span>
                </div>
                <div className="pf-field">
                  <span className="pf-label">Phone number</span>
                  <span className="pf-value">{phone || '—'}</span>
                </div>
              </div>
            </section>
          ) : (
            <form className="pf-card" id="profile-form" onSubmit={save} noValidate>
              <h3>Personal &amp; contact information</h3>
              <p className="pf-desc">Name and work email are managed by Borek. Phone number is optional.</p>
              <div className="pf-row">
                <div className="pf-field">
                  <label className="pf-label" htmlFor="pf-fn">First name</label>
                  <input id="pf-fn" value={firstName} readOnly />
                </div>
                <div className="pf-field">
                  <label className="pf-label" htmlFor="pf-ln">Last name</label>
                  <input id="pf-ln" value={lastName} readOnly />
                </div>
              </div>
              <div className="pf-row">
                <div className="pf-field">
                  <label className="pf-label" htmlFor="pf-em">Work email</label>
                  <input id="pf-em" type="email" value={user.email} readOnly />
                </div>
                <div className="pf-field">
                  <label className="pf-label" htmlFor="pf-ph">Phone number (optional)</label>
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
                <button type="button" className="pf-btn" onClick={cancel}>Cancel</button>
                <button type="submit" form="profile-form" className="pf-btn primary">Save changes</button>
              </>
            )}
            {mode === 'saved' && (
              <>
                <span className="pf-saved" role="status">Changes saved just now</span>
                <button type="button" className="pf-btn primary" onClick={() => setMode('view')}>Done</button>
              </>
            )}
          </div>}
        </div>

        <aside className="pf-secondary">
          <section className="pf-card">
            <h3>Preferences</h3>
            <div className="pf-pref">
              <label className="pf-label" htmlFor="pf-lang">Language</label>
              <div className="pf-select">
                <select id="pf-lang" value={language} onChange={(e) => setLanguage(e.target.value)}>
                  <option value="en">English (EN)</option>
                  <option value="de">Deutsch (DE)</option>
                </select>
                <img src={chevronIcon} alt="" />
              </div>
            </div>
            <div className="pf-pref">
              <span className="pf-label">Theme</span>
              <div className="pf-toggle-row">
                <div>
                  <strong>{dark ? 'Dark mode' : 'Light mode'}</strong>
                </div>
                <button
                  type="button"
                  className="pf-toggle"
                  role="switch"
                  aria-checked={dark}
                  aria-label="Dark mode"
                  onClick={() => setDark((d) => !d)}
                >
                  <img src={toggleOffIcon} alt="" />
                </button>
              </div>
            </div>
          </section>

          <section className="pf-card">
            <h3>Account &amp; security</h3>
            <p className="pf-desc">Manage access to your Borek account.</p>
            <div className="pf-setting">
              <div>
                <strong>Password</strong>
              </div>
              <button type="button" className="pf-link">Change</button>
            </div>
            <div className="pf-account">
              <button
                type="button"
                className="pf-link"
                onClick={() => {
                  signOut();
                  navigate(paths.login, { replace: true });
                }}
              >
                Sign out
              </button>
              <div className="pf-deactivate">
                <button type="button" className="pf-link danger">Deactivate account</button>
                <small>Requires confirmation</small>
              </div>
            </div>
          </section>
        </aside>
      </div>

      {confirmDiscard && (
        <div className="pf-overlay" role="dialog" aria-modal="true" aria-labelledby="pf-dlg-title" aria-describedby="pf-dlg-msg">
          <div className="pf-dialog">
            <h2 id="pf-dlg-title">Discard unsaved changes?</h2>
            <p id="pf-dlg-msg">Your profile changes haven’t been saved. You can keep editing or discard them.</p>
            <div className="pf-actions">
              <button ref={keepEditingRef} type="button" className="pf-btn" onClick={() => setConfirmDiscard(false)}>
                Keep editing
              </button>
              <button type="button" className="pf-btn primary" onClick={discard}>Discard changes</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
