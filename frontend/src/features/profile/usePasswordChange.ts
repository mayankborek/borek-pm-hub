import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { useAuth } from '@/features/auth/AuthContext';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { MIN_PASSWORD_LENGTH, useChangePassword } from './meApi';

/** State and submit for the "change your password" form. The server ends every session on success, so the person signs in again. */
export function usePasswordChange() {
  const { t } = usePrefs();
  const { signOut } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const change = useChangePassword();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');

  const submit = async () => {
    setError('');
    if (!current) return setError(t('Enter your current password.'));
    if (next.length < MIN_PASSWORD_LENGTH) return setError(t('The new password needs at least {n} characters.', { n: MIN_PASSWORD_LENGTH }));
    if (next !== confirm) return setError(t('The new passwords do not match.'));
    try {
      await change.mutateAsync({ current_password: current, new_password: next });
    } catch (e) {
      return setError(describeApiError(e, t('That didn’t work. Try again.')));
    }
    toast.success(t('Password changed. Sign in again with the new password.'));
    await signOut();
    navigate(paths.login, { replace: true });
  };

  return { current, setCurrent, next, setNext, confirm, setConfirm, error, busy: change.isPending, submit };
}
