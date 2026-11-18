export type ClientHealth = 'on_track' | 'at_risk' | 'off_track';
export type MilestoneState = 'done' | 'late' | 'revised' | 'at_risk' | 'in_progress' | 'planned';
export type ChangeRequestStatus = 'in_review' | 'approved' | 'declined';

export interface ClientMilestone {
  id: string;
  /** Short reference shown on the milestone card, e.g. M-01. */
  code: string;
  name: string;
  /** ISO date (YYYY-MM-DD). */
  dueDate: string;
  state: MilestoneState;
  progress: number;
  /** A later date: proposed while the change request is open, published once the state is `revised`. */
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

export interface ClientContact {
  name: string;
  role: string;
  email: string;
  phone?: string;
}

export interface ClientNotification {
  id: string;
  headline: string;
  meta: string;
  /** App path the notification opens. */
  to: string;
  unread: boolean;
}

export interface ClientUpdate {
  id: string;
  title: string;
  meta: string;
}

export interface ClientProject {
  id: string;
  /** Reference shown on the projects list, e.g. BF-024. */
  code: string;
  name: string;
  category: string;
  /** ISO dates. */
  startDate: string;
  dueDate: string;
  /** Open items waiting on the client. */
  clientActions: number;
  /** Optional line under the progress bar on the dashboard; falls back to the next milestone. */
  note?: string;
  /** The PM's latest written update. */
  latestUpdate?: { text: string; date: string };
  health: ClientHealth;
  /** Latest progress the PM published, not live task data. */
  progress: number;
  publishedOn: string;
  publishedBy: { name: string; role: string };
  contacts: ClientContact[];
  milestones: ClientMilestone[];
  changeRequests: ClientChangeRequest[];
  reports: ClientReport[];
}

export interface ClientPortalData {
  /** The date the portal treats as "today" (milestones before it are behind us). */
  today: string;
  /** The client organisation the projects belong to. */
  organisation: string;
  notifications: ClientNotification[];
  updates: ClientUpdate[];
  projects: ClientProject[];
}
