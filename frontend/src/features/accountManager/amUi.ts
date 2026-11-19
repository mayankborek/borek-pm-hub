import type { ClientHealth, MilestoneState } from '@/features/client/types';

/** Badge class from the design: green by default, red for late or off track, grey outline for planned. */
export const healthBadge = (h: ClientHealth) => (h === 'on_track' ? 'badge' : 'badge late');

export const milestoneBadge = (s: MilestoneState) =>
  s === 'done' ? 'badge' : s === 'late' || s === 'at_risk' ? 'badge late' : 'badge plan';
