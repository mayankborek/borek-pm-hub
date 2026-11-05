import { api, ApiError } from '@/shared/api/client';
import { ProviderUnavailableError } from '../authService';

export class InvitationUnavailableError extends Error {}

export interface Invitation {
  projectName: string;
  inviterName: string;
  email: string;
  roleLabel: string;
  expiresAt: string;
}

interface InvitationOut {
  project_name: string;
  inviter_name: string;
  email: string;
  role_label: string;
  expires_at: string;
}

/**
 * GET /invitations/{token}: what the invitation grants. 404 (unknown) and 410 (expired or revoked)
 * both mean the link can no longer be used.
 */
export async function fetchInvitation(token: string): Promise<Invitation> {
  try {
    const i = await api<InvitationOut>(`/invitations/${encodeURIComponent(token)}`);
    return {
      projectName: i.project_name,
      inviterName: i.inviter_name,
      email: i.email,
      roleLabel: i.role_label,
      expiresAt: i.expires_at,
    };
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 410)) throw new InvitationUnavailableError();
    throw e;
  }
}

/** Microsoft verifies the identity; needs the same Entra configuration as staff sign-in, so not available yet. */
export async function createAccountWithMicrosoft(): Promise<void> {
  throw new ProviderUnavailableError();
}
