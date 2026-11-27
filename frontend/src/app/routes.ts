import type { Role } from '@/features/auth/types';

/** Single source of truth for URLs. Never hardcode paths in components. */
export const paths = {
  login: '/login',
  setPassword: '/set-password',
  dashboard: '/dashboard',
  myWork: '/my-work',
  projects: '/projects',
  projectNew: '/projects/new',
  project: (id: string) => `/projects/${id}`,
  projectEdit: (id: string) => `/projects/${id}/edit`,
  projectBoard: (id: string) => `/projects/${id}/board`,
  projectList: (id: string) => `/projects/${id}/list`,
  projectSprintPlanning: (id: string) => `/projects/${id}/sprint-planning`,
  projectMembers: (id: string) => `/projects/${id}/members`,
  projectMilestones: (id: string) => `/projects/${id}/milestones`,
  projectSettings: (id: string) => `/projects/${id}/settings`,
  projectSettingsPeople: (id: string) => `/projects/${id}/settings/people`,
  projectChangeRequests: (id: string) => `/projects/${id}/change-requests`,
  projectRequirement: (id: string, requirementId: string) => `/projects/${id}/change-requests/requirements/${requirementId}`,
  projectChangeRequest: (id: string, crId: string) => `/projects/${id}/change-requests/${crId}`,
  projectReports: (id: string) => `/projects/${id}/reports`,
  projectReport: (id: string, reportId: string) => `/projects/${id}/reports/${reportId}`,
  profile: '/profile',
  pmSecurity: '/profile/security',
  pmNotifications: '/profile/notifications',
  pmPreferences: '/profile/preferences',
  tasks: '/tasks',
  taskNew: '/tasks/new',
  task: (id: string) => `/tasks/${id}`,
  forbidden: '/forbidden',
  clientLogin: '/client/login',
  clientInvitationLink: '/client/invitation',
  clientInvitation: (token: string) => `/client/invitation/${encodeURIComponent(token)}`,
  clientCreateAccount: '/client/create-account',
  clientAccountReady: '/client/account-ready',
  clientAccessUnavailable: '/client/access-unavailable',
  clientHome: '/client',
  clientProfile: '/client/profile',
  clientSecurity: '/client/profile/security',
  clientNotifications: '/client/profile/notifications',
  clientPreferences: '/client/profile/preferences',
  clientProjects: '/client/projects',
  clientProject: (id: string) => `/client/projects/${id}`,
  clientMilestones: (id: string) => `/client/projects/${id}/milestones`,
  clientReports: (id: string) => `/client/projects/${id}/reports`,
  clientReport: (id: string, reportId: string) => `/client/projects/${id}/reports/${reportId}`,
  clientChangeRequests: (id: string) => `/client/projects/${id}/change-requests`,
  clientRequirements: (id: string) => `/client/projects/${id}/requirements`,
  clientContacts: (id: string) => `/client/projects/${id}/contacts`,
  adminUsers: '/admin/users',
  adminUser: (id: string) => `/admin/users/${id}`,
  adminOrganisations: '/admin/organisations',
  adminOrganisationNew: '/admin/organisations/new',
  adminOrganisation: (id: string) => `/admin/organisations/${id}`,
  adminAccess: '/admin/access',
  adminRoles: '/admin/access/roles',
  adminAccessPerson: (userId: string) => `/admin/access/people/${userId}`,
  adminAccessProject: (userId: string, projectId: string) => `/admin/access/people/${userId}/${projectId}`,
  adminProfile: '/admin/profile',
  adminSecurity: '/admin/profile/security',
  adminNotifications: '/admin/profile/notifications',
  adminPreferences: '/admin/profile/preferences',
  managerHome: '/manager',
  managerProfile: '/manager/profile',
  managerSecurity: '/manager/profile/security',
  managerNotifications: '/manager/profile/notifications',
  managerPreferences: '/manager/profile/preferences',
  managerProjects: '/manager/projects',
  managerProject: (id: string) => `/manager/projects/${id}`,
  managerMilestones: (id: string) => `/manager/projects/${id}/milestones`,
  managerReports: (id: string) => `/manager/projects/${id}/reports`,
  managerReport: (id: string, reportId: string) => `/manager/projects/${id}/reports/${reportId}`,
  managerChangeRequests: (id: string) => `/manager/projects/${id}/change-requests`,
  managerChangeRequest: (id: string, requestId: string) => `/manager/projects/${id}/change-requests/${requestId}`,
  managerStakeholders: (id: string) => `/manager/projects/${id}/stakeholders`,
  managerTeam: '/manager/team',
  amHome: '/account-manager',
  amProfile: '/account-manager/profile',
  amProjects: '/account-manager/projects',
  amProject: (id: string) => `/account-manager/projects/${id}`,
  amTasks: '/account-manager/tasks',
  amBacklog: (id: string) => `/account-manager/projects/${id}/backlog`,
  amBoard: (id: string) => `/account-manager/projects/${id}/board`,
  amChangeRequests: (id: string) => `/account-manager/projects/${id}/change-requests`,
  amMilestones: (id: string) => `/account-manager/projects/${id}/milestones`,
  amReports: (id: string) => `/account-manager/projects/${id}/reports`,
  amReport: (id: string, reportId: string) => `/account-manager/projects/${id}/reports/${reportId}`,
  amStakeholders: (id: string) => `/account-manager/projects/${id}/stakeholders`,
  amSecurity: '/account-manager/profile/security',
  amNotifications: '/account-manager/profile/notifications',
  amPreferences: '/account-manager/profile/preferences',
} as const;

/** Client pages carry the invitation token in the query string so the flow can resume at any step. */
export const withInvitation = (path: string, token: string | null) =>
  token ? `${path}?invitation=${encodeURIComponent(token)}` : path;

/** Landing page after sign-in: PM -> dashboard, Developer -> My Work, Client -> Home, Admin -> Users, Account Manager -> Overview, Manager -> Dashboard. */
export const homeFor = (role: Role) =>
  role === 'pm'
    ? paths.dashboard
    : role === 'client'
      ? paths.clientHome
      : role === 'admin'
        ? paths.adminUsers
        : role === 'account_manager'
          ? paths.amHome
          : role === 'manager'
            ? paths.managerHome
            : paths.myWork;

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
  { label: 'Projects', to: paths.projects, roles: ['pm'], icon: '▤' },
];
