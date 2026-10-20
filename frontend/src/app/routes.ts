import type { Role } from '@/features/auth/types';

/** Single source of truth for URLs. Never hardcode paths in components. */
export const paths = {
  login: '/login',
  dashboard: '/dashboard',
  myWork: '/my-work',
  projects: '/projects',
  projectNew: '/projects/new',
  project: (id: string) => `/projects/${id}`,
  projectEdit: (id: string) => `/projects/${id}/edit`,
  projectBoard: (id: string) => `/projects/${id}/board`,
  projectList: (id: string) => `/projects/${id}/list`,
  projectMembers: (id: string) => `/projects/${id}/members`,
  profile: '/profile',
  tasks: '/tasks',
  task: (id: string) => `/tasks/${id}`,
  forbidden: '/forbidden',
} as const;

/** Landing page after sign-in: PM -> dashboard, Developer -> My Work. */
export const homeFor = (role: Role) => (role === 'pm' ? paths.dashboard : paths.myWork);

export interface NavItem {
  label: string;
  to: string;
  roles: Role[];
  icon: string;
}

/** Sidebar entries, filtered by the current user's role. */
export const navItems: NavItem[] = [
  { label: 'Dashboard', to: paths.dashboard, roles: ['pm'], icon: '▦' },
  { label: 'My Work', to: paths.myWork, roles: ['developer'], icon: '✓' },
  { label: 'Task List', to: paths.tasks, roles: ['pm', 'developer'], icon: '☰' },
];
