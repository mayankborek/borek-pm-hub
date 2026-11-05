import { initialLang, type Lang } from '../loginStrings';

export { initialLang };
export type { Lang };

interface ClientStrings {
  loading: string;
  loadFailed: string;
  // invitation
  inviteTitle: string;
  inviteBody: (inviter: string) => string;
  invitedAccount: string;
  inviteMeta: (role: string, expires: string) => string;
  openInvitation: string;
  newHere: string;
  // create account
  createTitle: string;
  createSub: string;
  fullName: string;
  fullNamePlaceholder: string;
  workEmail: string;
  nameRequired: string;
  microsoftNote: string;
  createWithMicrosoft: string;
  creating: string;
  accessNote: string;
  haveAccount: string;
  createFailed: string;
  // account ready
  readyTitle: string;
  readySub: string;
  workAccount: string;
  readyDesc: string;
  continueToWorkspace: string;
  backToSignIn: string;
  // unavailable
  unavailableTitle: string;
  unavailableBody: string;
  useInvitedAccount: string;
  requestNew: string;
  // sign in
  altLabel: string;
  forgot: string;
  showPassword: string;
  hidePassword: string;
  newToFlow: string;
  createAccount: string;
}

const en: ClientStrings = {
  loading: 'Loading…',
  loadFailed: 'We could not load your invitation. Try again in a moment.',
  inviteTitle: 'You’re invited to Borek Flow',
  inviteBody: (inviter) => `${inviter} invited you to review requirements, published progress and the product preview.`,
  invitedAccount: 'Invited account',
  inviteMeta: (role, expires) => `${role} · Expires ${expires}`,
  openInvitation: 'Open invitation',
  newHere: 'New here? Create an account',
  createTitle: 'Create your account',
  createSub: 'Create your account with your work email.',
  fullName: 'Full name',
  fullNamePlaceholder: 'Your full name',
  workEmail: 'Work email',
  nameRequired: 'Full name is required.',
  microsoftNote: 'Microsoft verifies your identity. You will not need a separate Borek Flow password.',
  createWithMicrosoft: 'Create account with Microsoft',
  creating: 'Creating account...',
  accessNote: 'Your organisation and project invitations determine your access.',
  haveAccount: 'Already have an account? Sign in',
  createFailed: 'Microsoft sign-up is not available yet. Try again later or contact the person who invited you.',
  readyTitle: 'Your account is ready',
  readySub: 'Your Microsoft identity has been verified. You can now continue to your workspace.',
  workAccount: 'Work account',
  readyDesc: 'Workspace access follows your organisation and project permissions.',
  continueToWorkspace: 'Continue to workspace',
  backToSignIn: 'Back to sign in',
  unavailableTitle: 'Access unavailable',
  unavailableBody: 'This invitation has expired or access is no longer available.',
  useInvitedAccount: 'Use the invited account',
  requestNew: 'To get a new invitation, contact the person who invited you.',
  altLabel: 'Or sign in with email and password',
  forgot: 'Forgot password?',
  showPassword: 'Show password',
  hidePassword: 'Hide password',
  newToFlow: 'New to Borek Flow?',
  createAccount: 'Create an account',
};

const de: ClientStrings = {
  loading: 'Wird geladen…',
  loadFailed: 'Ihre Einladung konnte nicht geladen werden. Versuchen Sie es gleich noch einmal.',
  inviteTitle: 'Sie wurden zu Borek Flow eingeladen',
  inviteBody: (inviter) =>
    `${inviter} hat Sie eingeladen, Anforderungen, veröffentlichte Fortschritte und die Produktvorschau zu prüfen.`,
  invitedAccount: 'Eingeladenes Konto',
  inviteMeta: (role, expires) => `${role} · Läuft ab am ${expires}`,
  openInvitation: 'Einladung öffnen',
  newHere: 'Neu hier? Konto erstellen',
  createTitle: 'Konto erstellen',
  createSub: 'Erstellen Sie Ihr Konto mit Ihrer geschäftlichen E-Mail-Adresse.',
  fullName: 'Vollständiger Name',
  fullNamePlaceholder: 'Ihr vollständiger Name',
  workEmail: 'Geschäftliche E-Mail',
  nameRequired: 'Der Name ist erforderlich.',
  microsoftNote: 'Microsoft bestätigt Ihre Identität. Sie benötigen kein separates Borek-Flow-Passwort.',
  createWithMicrosoft: 'Konto mit Microsoft erstellen',
  creating: 'Konto wird erstellt...',
  accessNote: 'Ihre Organisation und Projekteinladungen bestimmen Ihren Zugriff.',
  haveAccount: 'Bereits ein Konto? Anmelden',
  createFailed:
    'Die Registrierung mit Microsoft ist noch nicht verfügbar. Versuchen Sie es später erneut oder kontaktieren Sie die einladende Person.',
  readyTitle: 'Ihr Konto ist bereit',
  readySub: 'Ihre Microsoft-Identität wurde bestätigt. Sie können jetzt zu Ihrem Arbeitsbereich wechseln.',
  workAccount: 'Geschäftskonto',
  readyDesc: 'Der Zugriff auf den Arbeitsbereich richtet sich nach Ihrer Organisation und den Projektberechtigungen.',
  continueToWorkspace: 'Weiter zum Arbeitsbereich',
  backToSignIn: 'Zurück zur Anmeldung',
  unavailableTitle: 'Zugriff nicht verfügbar',
  unavailableBody: 'Diese Einladung ist abgelaufen oder der Zugriff ist nicht mehr verfügbar.',
  useInvitedAccount: 'Eingeladenes Konto verwenden',
  requestNew: 'Für eine neue Einladung wenden Sie sich an die einladende Person.',
  altLabel: 'Oder mit E-Mail und Passwort anmelden',
  forgot: 'Passwort vergessen?',
  showPassword: 'Passwort anzeigen',
  hidePassword: 'Passwort verbergen',
  newToFlow: 'Neu bei Borek Flow?',
  createAccount: 'Konto erstellen',
};

export const CLIENT_STRINGS: Record<Lang, ClientStrings> = { en, de };
