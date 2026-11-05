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
  taskNew: '/tasks/new',
  task: (id: string) => `/tasks/${id}`,
  forbidden: '/forbidden',
  clientLogin: '/client/login',
  clientInvitation: (token: string) => `/client/invitation/${encodeURIComponent(token)}`,
  clientCreateAccount: '/client/create-account',
  clientAccountReady: '/client/account-ready',
  clientAccessUnavailable: '/client/access-unavailable',
  clientHome: '/client',
  clientProfile: '/client/profile',
  clientProjects: '/client/projects',
  clientProject: (id: string) => `/client/projects/${id}`,
  clientMilestones: (id: string) => `/client/projects/${id}/milestones`,
  clientReports: (id: string) => `/client/projects/${id}/reports`,
  clientReport: (id: string, reportId: string) => `/client/projects/${id}/reports/${reportId}`,
  clientChangeRequests: (id: string) => `/client/projects/${id}/change-requests`,
  clientContacts: (id: string) => `/client/projects/${id}/contacts`,
  adminUsers: '/admin/users',
  adminOrganisations: '/admin/organisations',
  adminRoles: '/admin/roles',
} as const;

/** Client pages carry the invitation token in the query string so the flow can resume at any step. */
export const withInvitation = (path: string, token: string | null) =>
  token ? `${path}?invitation=${encodeURIComponent(token)}` : path;

/** Landing page after sign-in: PM -> dashboard, Developer -> My Work, Client -> Home, Admin -> Users. */
export const homeFor = (role: Role) =>
  role === 'pm' ? paths.dashboard : role === 'client' ? paths.clientHome : role === 'admin' ? paths.adminUsers : paths.myWork;

export interface NavItem {
  label: string;
  to: string;
  roles: Role[];
  icon: string;
}

/** Sidebar entries, filtered by the current user's role. */
export const navItems: NavItem[] = [
  { label: 'Dashboard', to: paths.dashboard, roles: ['pm'], icon: '▦' },
  { label: 'My Task', to: paths.myWork, roles: ['developer'], icon: '✓' },
  { label: 'Task List', to: paths.tasks, roles: ['pm'], icon: '☰' },
];
