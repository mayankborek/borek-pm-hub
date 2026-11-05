import type { ChangeRequestStatus, ClientHealth, MilestoneState } from './types';

/** The five badge tones from the client component sheet. Neutral is plain grey text. */
export type Tone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

export const HEALTH_LABEL: Record<ClientHealth, string> = {
  on_track: 'On track',
  at_risk: 'At risk',
  off_track: 'Off track',
};
export const HEALTH_TONE: Record<ClientHealth, Tone> = {
  on_track: 'success',
  at_risk: 'warning',
  off_track: 'danger',
};

export const CR_LABEL: Record<ChangeRequestStatus, string> = {
  in_review: 'In review',
  approved: 'Approved',
  declined: 'Declined',
};

/** Badge on a milestone card or row. */
export const MILESTONE_BADGE: Record<MilestoneState, { label: string; tone: Tone }> = {
  done: { label: 'Done', tone: 'success' },
  late: { label: 'Overdue', tone: 'danger' },
  revised: { label: 'Forecast revised', tone: 'info' },
  at_risk: { label: 'At risk', tone: 'warning' },
  in_progress: { label: 'In progress', tone: 'info' },
  planned: { label: 'Planned', tone: 'neutral' },
};

/** Status line under a milestone title on the curve, coloured as in the component sheet. */
export const MILESTONE_STATUS: Record<MilestoneState, { label: string; color: string; weight: number }> = {
  late: { label: 'Running late', color: '#AD1F1F', weight: 600 },
  revised: { label: 'Forecast revised', color: '#124F94', weight: 600 },
  at_risk: { label: 'At risk', color: '#0D1240', weight: 600 },
  in_progress: { label: 'In progress', color: '#0D1240', weight: 600 },
  done: { label: 'Completed', color: '#17735E', weight: 600 },
  planned: { label: 'Not started yet', color: '#5C6178', weight: 500 },
};

/** Numbered node fill; planned milestones are a dashed ring instead. */
export const NODE_FILL: Record<Exclude<MilestoneState, 'planned'>, string> = {
  late: '#C94A32',
  revised: '#124F94',
  in_progress: '#124F94',
  done: '#124F94',
  at_risk: '#E07E00',
};
