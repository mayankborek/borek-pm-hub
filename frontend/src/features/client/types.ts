export type ClientHealth = 'on_track' | 'at_risk' | 'off_track';
export type MilestoneState = 'done' | 'late' | 'revised' | 'at_risk' | 'in_progress' | 'planned';
export type ChangeRequestStatus = 'pending' | 'in_review' | 'approved' | 'declined';

export interface ClientMilestone {
  id: string;
  /** Short reference shown on the milestone card, e.g. M-01. */
  code: string;
  name: string;
  /** ISO date (YYYY-MM-DD). */
  dueDate: string;
  state: MilestoneState;
  /** 100 once reached; null = not available (never guessed from tasks). */
  progress: number | null;
  /** A later date: proposed while the change request is open, published once the state is `revised`. */
  requestedDate?: string;
  changeRequestRef?: string;
}

export type ProjectTaskStatus = 'To do' | 'In progress' | 'Code review' | 'Testing' | 'Blocked';

/** A task due date shown on the Account Manager roadmap. */
export interface ProjectTask {
  id: string;
  /** Ticket reference, shown before the title when present, e.g. BFL-112. */
  ref?: string;
  title: string;
  status: ProjectTaskStatus;
  /** ISO date (YYYY-MM-DD). */
  dueDate: string;
}

export interface ClientChangeRequest {
  ref: string;
  title: string;
  status: ChangeRequestStatus;
}

export interface ClientReport {
  id: string;
  title: string;
  /** ISO date the report is about. */
  reportDate: string;
  /** ISO date-time it was published to the client. */
  publishedAt: string;
  health: ClientHealth;
  summary: string;
  /** Progress the report shared; null when it shared none. */
  progress: number | null;
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
  startDate: string | null;
  dueDate: string | null;
  /** Open items waiting on the client. */
  clientActions: number;
  /** Optional line under the progress bar on the dashboard; falls back to the next milestone. */
  note?: string;
  /** The PM's latest written update. */
  latestUpdate?: { text: string; date: string };
  /** From the newest published report; null until the first one is published. */
  health: ClientHealth | null;
  /** Latest progress the PM published, not live task data; null = not published yet. */
  progress: number | null;
  publishedOn: string | null;
  publishedBy: { name: string; role: string } | null;
  /** The project lead's name; null = not assigned yet. */
  projectManager?: string | null;
  contacts: ClientContact[];
  milestones: ClientMilestone[];
  tasks?: ProjectTask[];
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
