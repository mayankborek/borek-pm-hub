import { api, ApiError } from '@/shared/api/client';
import { ProviderUnavailableError } from '../authService';

export class InvitationUnavailableError extends Error {}

export interface Invitation {
  organisationName: string;
  inviterName: string;
  email: string;
  roleLabel: string;
  expiresAt: string;
}

interface InviteInfoOut {
  email: string;
  name: string;
  role: string;
  role_label: string;
  organisation_name: string | null;
  inviter_name: string | null;
  expires_at: string;
}

const PREVIEW: Invitation = {
  organisationName: 'BRECO',
  inviterName: 'Alex Morgan',
  email: 'jordan.lee@customer.com',
  roleLabel: 'Client approver',
  expiresAt: '2026-11-06T00:00:00Z',
};

/**
 * POST /auth/invite-info: who the link is for, without using it up. The token travels in the body so it
 * stays out of access logs. Any 400 (unknown, used, expired or revoked) means the link can no longer be used.
 */
export async function fetchInvitation(token: string): Promise<Invitation> {
  // Dev only: /client/invitation/preview shows the screen without a backend invitation.
  if (import.meta.env.DEV && token === 'preview') return PREVIEW;
  try {
    const i = await api<InviteInfoOut>('/auth/invite-info', { method: 'POST', body: JSON.stringify({ token }) });
    return {
      organisationName: i.organisation_name ?? '',
      inviterName: i.inviter_name ?? 'Borek',
      email: i.email,
      roleLabel: i.role_label,
      expiresAt: i.expires_at,
    };
  } catch (e) {
    if (e instanceof ApiError && (e.status === 400 || e.status === 404 || e.status === 410)) throw new InvitationUnavailableError();
    throw e;
  }
}

/** Microsoft verifies the identity; needs the same Entra configuration as staff sign-in, so not available yet. */
export async function createAccountWithMicrosoft(): Promise<void> {
  throw new ProviderUnavailableError();
}
