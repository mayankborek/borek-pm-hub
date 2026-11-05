import type { ChangeRequestStatus, ClientHealth } from './types';

export const HEALTH_LABEL: Record<ClientHealth, string> = {
  on_track: 'On track',
  at_risk: 'At risk',
  off_track: 'Off track',
};

/** The design only has a green and a red badge; both problem states use the red one. */
export const HEALTH_TONE: Record<ClientHealth, 'late' | undefined> = {
  on_track: undefined,
  at_risk: 'late',
  off_track: 'late',
};

export const CR_LABEL: Record<ChangeRequestStatus, string> = {
  in_review: 'In review',
  approved: 'Approved',
  declined: 'Declined',
};
