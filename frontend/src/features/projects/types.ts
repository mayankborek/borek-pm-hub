export type ProjectStatus = 'planned' | 'active' | 'on_hold' | 'completed' | 'cancelled';
export type TaskStatus = 'open' | 'in_progress' | 'blocked' | 'in_review' | 'completed' | 'cancelled';

export const PROJECT_STATUSES: ProjectStatus[] = ['planned', 'active', 'on_hold', 'completed', 'cancelled'];

/** Shared list envelope (architecture doc, section 9). */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/**
 * Per-project task counts returned with the project list. Excludes cancelled
 * tasks; overdue = due before today and not completed/cancelled.
 * Optional until the backend ticket for projects lands.
 */
export interface TaskSummary {
  total: number;
  completed: number;
  in_progress: number;
  blocked: number;
  overdue: number;
  completion_percent: number;
}

export interface Project {
  id: string;
  code: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  start_date: string | null;
  target_end_date: string | null;
  /** Optimistic-locking counter, sent back on PATCH. */
  version: number;
  task_summary?: TaskSummary | null;
}

export interface ProjectInput {
  code: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  start_date: string | null;
  target_end_date: string | null;
}

/** Subset of GET /tasks used by the dashboard's attention list. */
export interface TaskListItem {
  id: string;
  key: string;
  title: string;
  status: TaskStatus;
  due_date: string | null;
  project_id: string;
  project_name?: string;
}
