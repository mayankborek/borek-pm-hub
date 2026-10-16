export type Lang = 'en' | 'de';

export const LOGIN_STRINGS = {
  en: {
    heroTitle: 'Work, Moving Forward.',
    heroText: 'One workspace for project plans, team tasks, and delivery progress.',
    footer: 'Borek Flow · Secure workspace',
    welcome: 'Welcome back',
    sub: 'Sign in with your company account. Your access and workspace will load automatically.',
    microsoft: 'Continue with Microsoft',
    email: 'Email *',
    password: 'Password *',
    emailInvalid: 'Email format is invalid.',
    passwordRequired: 'Password is required.',
    login: 'Login',
    signingIn: 'Signing in...',
    keepSignedIn: 'Keep me signed in on this device',
    errorTitle: 'Check your sign-in details',
    errorText: 'Try again or reset your company password.',
    noAccessTitle: 'No workspace access',
    noAccessText: 'Contact your workspace administrator to request an account.',
    language: 'Language',
    help: 'Need access? Contact your workspace administrator.',
  },
  de: {
    heroTitle: 'Arbeiten, immer vorwärts.',
    heroText: 'Ein Arbeitsbereich für Projektpläne, Teamaufgaben und Lieferfortschritt.',
    footer: 'Borek Flow · Sicherer Arbeitsbereich',
    welcome: 'Willkommen zurück',
    sub: 'Melden Sie sich mit Ihrem Firmenkonto an. Ihr Zugriff und Arbeitsbereich werden automatisch geladen.',
    microsoft: 'Weiter mit Microsoft',
    email: 'E-Mail *',
    password: 'Passwort *',
    emailInvalid: 'Das E-Mail-Format ist ungültig.',
    passwordRequired: 'Passwort ist erforderlich.',
    login: 'Anmelden',
    signingIn: 'Anmeldung läuft...',
    keepSignedIn: 'Auf diesem Gerät angemeldet bleiben',
    errorTitle: 'Überprüfen Sie Ihre Anmeldedaten',
    errorText: 'Versuchen Sie es erneut oder setzen Sie Ihr Firmenpasswort zurück.',
    noAccessTitle: 'Kein Zugriff auf den Arbeitsbereich',
    noAccessText: 'Wenden Sie sich an Ihren Administrator, um ein Konto anzufordern.',
    language: 'Sprache',
    help: 'Zugriff benötigt? Wenden Sie sich an Ihren Administrator.',
  },
} as const;

export function initialLang(): Lang {
  const q = new URLSearchParams(window.location.search).get('lang');
  if (q === 'de' || q === 'en') return q;
  const saved = localStorage.getItem('lang');
  return saved === 'de' ? 'de' : 'en';
}
