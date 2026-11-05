export type ClientHealth = 'on_track' | 'at_risk' | 'off_track';
export type MilestoneState = 'done' | 'late' | 'in_progress' | 'planned';
export type ChangeRequestStatus = 'in_review' | 'approved' | 'declined';

export interface ClientMilestone {
  id: string;
  name: string;
  /** ISO date (YYYY-MM-DD). */
  dueDate: string;
  state: MilestoneState;
  progress: number;
  /** Only when the client has asked for a later date through a change request. */
  requestedDate?: string;
  changeRequestRef?: string;
}

export interface ClientChangeRequest {
  ref: string;
  title: string;
  status: ChangeRequestStatus;
}

export interface ClientReport {
  id: string;
  title: string;
  periodStart: string;
  periodEnd: string;
  createdOn: string;
  summary: string;
  forecast: string;
  progress: number;
}

export interface ClientProject {
  id: string;
  name: string;
  health: ClientHealth;
  /** Latest progress the PM published, not live task data. */
  progress: number;
  publishedOn: string;
  publishedBy: { name: string; role: string };
  milestones: ClientMilestone[];
  changeRequests: ClientChangeRequest[];
  reports: ClientReport[];
}

export interface ClientPortalData {
  /** The date the portal treats as "today" (milestones before it are behind us). */
  today: string;
  projects: ClientProject[];
}
