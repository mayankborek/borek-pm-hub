import { useEffect, useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { paths, withInvitation } from '@/app/routes';
import { ClientAuthShell, useClientLang } from './ClientAuthShell';
import { createAccountWithMicrosoft, InvitationUnavailableError } from './clientAuthService';
import { useInvitation } from './useInvitation';

const formatDate = (iso: string, lang: string) =>
  new Date(iso).toLocaleDateString(lang === 'de' ? 'de-DE' : 'en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });

/** 01 · Invitation: the landing page of the emailed link. */
export function ClientInvitePage() {
  const { token = '' } = useParams();
  const { lang, t } = useClientLang();
  const invitation = useInvitation(token);

  if (invitation.error instanceof InvitationUnavailableError) {
    return <Navigate to={paths.clientAccessUnavailable} replace />;
  }
  const data = invitation.data;

  return (
    <ClientAuthShell lang={lang}>
      {invitation.isError ? (
        <p className="body" role="alert">{t.loadFailed}</p>
      ) : !data ? (
        <p className="body" role="status">{t.loading}</p>
      ) : (
        <>
          <h2 className="title">{t.inviteTitle}</h2>
          <h3 className="project">{data.projectName}</h3>
          <p className="body">{t.inviteBody(data.inviterName)}</p>
          <div className="card">
            <p className="label">{t.invitedAccount}</p>
            <p className="value">{data.email}</p>
            <p className="meta">{t.inviteMeta(data.roleLabel, formatDate(data.expiresAt, lang))}</p>
          </div>
          <Link className="btn" to={withInvitation(paths.clientLogin, token)}>{t.openInvitation}</Link>
          <Link className="btn secondary" to={withInvitation(paths.clientCreateAccount, token)}>{t.newHere}</Link>
        </>
      )}
    </ClientAuthShell>
  );
}

/** 02 · Create account: the invited email is fixed, Microsoft verifies the identity. */
export function ClientCreateAccountPage() {
  const { lang, t, login } = useClientLang();
  const navigate = useNavigate();
  const invitation = useInvitation();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [nameError, setNameError] = useState<string>();
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  const invitedEmail = invitation.data?.email;
  useEffect(() => {
    if (invitedEmail) setEmail(invitedEmail);
  }, [invitedEmail]);

  if (invitation.error instanceof InvitationUnavailableError) {
    return <Navigate to={paths.clientAccessUnavailable} replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setNameError(t.nameRequired);
      return;
    }
    setNameError(undefined);
    setFailed(false);
    setBusy(true);
    try {
      await createAccountWithMicrosoft();
      navigate(withInvitation(paths.clientAccountReady, invitation.token), { replace: true });
    } catch {
      setFailed(true);
      setBusy(false);
    }
  };

  return (
    <ClientAuthShell lang={lang} busy={busy}>
      <h2>{t.createTitle}</h2>
      <p className="sub">{t.createSub}</p>

      <form noValidate onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="full-name">{t.fullName}</label>
          <input
            id="full-name"
            type="text"
            autoComplete="name"
            placeholder={t.fullNamePlaceholder}
            value={name}
            disabled={busy}
            aria-invalid={nameError ? true : undefined}
            aria-describedby={nameError ? 'name-err' : undefined}
            onChange={(e) => setName(e.target.value)}
          />
          {nameError && <p className="field-err" id="name-err">{nameError}</p>}
        </div>
        <div className="field">
          <label htmlFor="work-email">{t.workEmail}</label>
          <input
            id="work-email"
            type="email"
            autoComplete="email"
            placeholder="name@company.com"
            value={email}
            readOnly={!!invitedEmail}
            disabled={busy}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <p className="note">{t.microsoftNote}</p>
        <button type="submit" className="btn" disabled={busy}>
          {busy ? t.creating : t.createWithMicrosoft}
        </button>

        {failed && (
          <div className="status error" role="alert">
            <strong>{login.errorTitle}</strong>
            <span>{t.createFailed}</span>
          </div>
        )}

        <p className="note">{t.accessNote}</p>
        <Link className="btn secondary" to={withInvitation(paths.clientLogin, invitation.token)}>{t.haveAccount}</Link>
      </form>
    </ClientAuthShell>
  );
}

/** 03 · Account ready. */
export function ClientAccountReadyPage() {
  const { lang, t } = useClientLang();
  const invitation = useInvitation();
  const signIn = withInvitation(paths.clientLogin, invitation.token);

  return (
    <ClientAuthShell lang={lang}>
      <h2>{t.readyTitle}</h2>
      <p className="sub">{t.readySub}</p>
      <div className="card">
        <p className="label">{t.workAccount}</p>
        {invitation.data && <p className="value">{invitation.data.email}</p>}
        <p className="meta">{t.readyDesc}</p>
      </div>
      <Link className="btn" to={signIn}>{t.continueToWorkspace}</Link>
      <Link className="btn secondary" to={signIn}>{t.backToSignIn}</Link>
    </ClientAuthShell>
  );
}

/** 04 · Access unavailable: expired, revoked or unknown invitation. */
export function ClientAccessUnavailablePage() {
  const { lang, t } = useClientLang();
  const invitation = useInvitation();

  return (
    <ClientAuthShell lang={lang}>
      <h2 className="title">{t.unavailableTitle}</h2>
      <p className="body">{t.unavailableBody}</p>
      <Link className="btn" to={withInvitation(paths.clientLogin, invitation.token)}>{t.useInvitedAccount}</Link>
      <p className="note">{t.requestNew}</p>
    </ClientAuthShell>
  );
}
