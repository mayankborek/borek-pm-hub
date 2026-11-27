import { createBrowserRouter, Navigate } from 'react-router-dom';
import { paths } from './routes';
import { AppLayout } from '@/layouts/AppLayout';
import { LoginPage } from '@/features/auth/LoginPage';
import { SetPasswordPage } from '@/features/auth/SetPasswordPage';
import { ForgotPasswordPage } from '@/features/auth/ForgotPasswordPage';
import { ClientLoginPage } from '@/features/auth/client/ClientLoginPage';
import {
  ClientAccessUnavailablePage,
  ClientAccountReadyPage,
  ClientCreateAccountPage,
  ClientInvitePage,
} from '@/features/auth/client/ClientPages';
import { ClientLayout } from '@/features/client/ClientLayout';
import { ClientHomePage } from '@/features/client/ClientHomePage';
import { ClientProjectsPage } from '@/features/client/ClientProjectsPage';
import { ClientProjectLayout } from '@/features/client/ClientProjectLayout';
import { ClientOverviewPage } from '@/features/client/ClientOverviewPage';
import { AmMilestonesPage } from '@/features/accountManager/AmMilestonesPage';
import { ClientMilestonesPage } from '@/features/client/ClientMilestonesPage';
import { ProjectChangeRequestsPage } from '@/features/changeRequests/ProjectChangeRequestsPage';
import { RequirementDetailPage } from '@/features/requirements/RequirementDetailPage';
import { ProjectChangeRequestPage } from '@/features/changeRequests/ProjectChangeRequestPage';
import { ProjectReportsPage, ProjectReportPage } from '@/features/reports/ProjectReportsPages';
import { ClientChangeRequestsPage } from '@/features/client/ClientChangeRequestsPage';
import { ClientContactsPage } from '@/features/client/ClientContactsPage';
import { ClientReportPage, ClientReportsPage } from '@/features/client/ClientReportsPages';
import { AccountManagerLayout } from '@/features/accountManager/AccountManagerLayout';
import { StakeholdersPage } from '@/features/accountManager/StakeholdersPage';
import { ManagerLayout } from '@/features/manager/ManagerLayout';
import { ManagerDashboardPage } from '@/features/manager/ManagerDashboardPage';
import { ManagerStakeholdersPage } from '@/features/manager/ManagerStakeholdersPage';
import { ManagerTeamPage } from '@/features/manager/ManagerTeamPage';
import { AmTasksPage } from '@/features/accountManager/AmTasksPage';
import { AmBacklogPage, AmBoardPage, AmChangeRequestsPage } from '@/features/accountManager/AmBoardPages';
import { AmHomePage } from '@/features/accountManager/AmHomePage';
import { AmProjectsPage } from '@/features/accountManager/AmProjectsPage';
import { AmProjectLayout } from '@/features/accountManager/AmProjectLayout';
import { AmOverviewPage } from '@/features/accountManager/AmOverviewPage';
import { AmNotificationsPage, AmPreferencesPage, AmProfilePage, AmSecurityPage, PmSettings } from '@/features/accountManager/AmSettingsPages';
import { AdminLayout } from '@/features/admin/AdminLayout';
import { AdminUsersPage } from '@/features/admin/AdminUsersPage';
import { AdminOrganisationsPage } from '@/features/admin/AdminOrganisationsPage';
import { AdminOrganisationFormPage } from '@/features/admin/AdminOrganisationFormPage';
import { AdminAccessPage, AdminPersonAccessPage } from '@/features/admin/AdminAccessPages';
import { AdminSettingsPage } from '@/features/admin/AdminSettingsPages';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { ProjectsPage } from '@/features/projects/ProjectsPage';
import { ProjectLayout } from '@/features/projects/ProjectLayout';
import { ProjectCreatePage, ProjectEditPage } from '@/features/projects/ProjectFormPage';
import { ProjectOverviewPage } from '@/features/projects/ProjectOverviewPage';
import { ProjectBoardPage } from '@/features/projects/ProjectBoardPage';
import { SprintPlanningPage } from '@/features/projects/SprintPlanningPage';
import { ProjectListPage, ProjectMembersPage } from '@/features/projects/ProjectViews';
import { MilestonesPage } from '@/features/milestones/MilestonesPage';
import { ProjectMemberPage, ProjectPeoplePage, ProjectSettingsPage } from '@/features/projects/ProjectSettingsPages';
import { TasksPage } from '@/features/tasks/TaskPages';
import { TaskCreatePage } from '@/features/tasks/TaskCreatePage';
import { MyWorkPage } from '@/features/tasks/MyWorkPage';
import { TaskDetailPage } from '@/features/tasks/TaskDetailPage';
import { ManagerChangeRequestPage, ManagerChangeRequestsPage } from '@/features/changeRequests/ManagerChangeRequests';
import { DeveloperLayout } from '@/features/developer/DeveloperLayout';
import { DevProjectLayout } from '@/features/developer/DevProjectLayout';
import { DevOverviewPage } from '@/features/developer/DevOverviewPage';
import { DevBacklogPage } from '@/features/developer/DevBacklogPage';
import { DevBoardPage } from '@/features/developer/DevBoardPage';
import { ForbiddenPage, NotFoundPage } from '@/features/errors/ErrorPages';
import { ByRole, RedirectIfAuthed, RequireAuth, RequireRole, RoleHome, StaffOnly } from './guards';

export const router = createBrowserRouter([
  // Public, reachable even while signed in (an administrator may open a link in their own browser)
  { path: 'set-password', element: <SetPasswordPage /> },
  { path: 'forgot-password', element: <ForgotPasswordPage /> },

  // Public
  {
    element: <RedirectIfAuthed />,
    children: [
      { path: 'login', element: <LoginPage /> },
      { path: 'client/login', element: <ClientLoginPage /> },
      { path: 'client/invitation', element: <ClientInvitePage /> },
      { path: 'client/invitation/:token', element: <ClientInvitePage /> },
      { path: 'client/create-account', element: <ClientCreateAccountPage /> },
      { path: 'client/account-ready', element: <ClientAccountReadyPage /> },
      { path: 'client/access-unavailable', element: <ClientAccessUnavailablePage /> },
    ],
  },

  // Authenticated app shell
  {
    element: <RequireAuth />,
    children: [
      // Client portal: its own shell, invited clients only
      {
        element: <RequireRole roles={['client']} />,
        children: [
          {
            path: 'client',
            element: <ClientLayout />,
            children: [
              { index: true, element: <ClientHomePage /> },
              { path: 'profile', element: <AmProfilePage /> },
              { path: 'profile/security', element: <AmSecurityPage /> },
              { path: 'profile/notifications', element: <AmNotificationsPage /> },
              { path: 'profile/preferences', element: <AmPreferencesPage /> },
              { path: 'projects', element: <ClientProjectsPage /> },
              {
                path: 'projects/:projectId',
                element: <ClientProjectLayout />,
                children: [
                  { index: true, element: <ClientOverviewPage /> },
                  { path: 'milestones', element: <ClientMilestonesPage /> },
                  { path: 'reports', element: <ClientReportsPage /> },
                  { path: 'reports/:reportId', element: <ClientReportPage /> },
                  { path: 'change-requests', element: <ClientChangeRequestsPage /> },
                  { path: 'contacts', element: <ClientContactsPage /> },
                ],
              },
            ],
          },
        ],
      },
      // Account Manager portal: its own shell, reuses the client screens (sample data until the API exists)
      {
        element: <RequireRole roles={['account_manager']} />,
        children: [
          {
            path: 'account-manager',
            element: <AccountManagerLayout />,
            children: [
              { index: true, element: <AmHomePage /> },
              { path: 'profile', element: <AmProfilePage /> },
              { path: 'profile/security', element: <AmSecurityPage /> },
              { path: 'profile/notifications', element: <AmNotificationsPage /> },
              { path: 'profile/preferences', element: <AmPreferencesPage /> },
              { path: 'tasks', element: <AmTasksPage /> },
              { path: 'projects', element: <AmProjectsPage /> },
              {
                path: 'projects/:projectId',
                element: <AmProjectLayout />,
                children: [
                  { index: true, element: <AmOverviewPage /> },
                  { path: 'backlog', element: <AmBacklogPage /> },
                  { path: 'board', element: <AmBoardPage /> },
                  { path: 'change-requests', element: <AmChangeRequestsPage /> },
                  { path: 'milestones', element: <AmMilestonesPage /> },
                  { path: 'reports', element: <ClientReportsPage /> },
                  { path: 'reports/:reportId', element: <ClientReportPage /> },
                  { path: 'stakeholders', element: <StakeholdersPage /> },
                ],
              },
            ],
          },
        ],
      },
      // Manager: own shell with the dashboard, project tabs, team and account screens (sample data until the API exists)
      {
        element: <RequireRole roles={['manager']} />,
        children: [
          {
            path: 'manager',
            element: <ManagerLayout />,
            children: [
              { index: true, element: <ManagerDashboardPage /> },
              { path: 'profile', element: <AmProfilePage /> },
              { path: 'profile/security', element: <AmSecurityPage /> },
              { path: 'profile/notifications', element: <AmNotificationsPage /> },
              { path: 'profile/preferences', element: <AmPreferencesPage /> },
              { path: 'projects', element: <ClientProjectsPage /> },
              {
                path: 'projects/:projectId',
                element: <ClientProjectLayout />,
                children: [
                  { index: true, element: <ClientOverviewPage /> },
                  { path: 'milestones', element: <ClientMilestonesPage /> },
                  { path: 'reports', element: <ClientReportsPage /> },
                  { path: 'reports/:reportId', element: <ClientReportPage /> },
                  { path: 'change-requests', element: <ManagerChangeRequestsPage /> },
                  { path: 'change-requests/:requestId', element: <ManagerChangeRequestPage /> },
                  { path: 'stakeholders', element: <ManagerStakeholdersPage /> },
                ],
              },
              { path: 'team', element: <ManagerTeamPage /> },
            ],
          },
        ],
      },
      // Admin console: its own shell, administrators only
      {
        element: <RequireRole roles={['admin']} />,
        children: [
          {
            path: 'admin',
            element: <AdminLayout />,
            children: [
              { index: true, element: <Navigate to={paths.adminUsers} replace /> },
              { path: 'users', element: <AdminUsersPage /> },
              { path: 'users/:userId', element: <AdminUsersPage /> },
              { path: 'organisations', element: <AdminOrganisationsPage /> },
              { path: 'organisations/new', element: <AdminOrganisationFormPage /> },
              { path: 'organisations/:orgId', element: <AdminOrganisationFormPage /> },
              { path: 'access', element: <AdminAccessPage tab="people" /> },
              { path: 'access/roles', element: <AdminAccessPage tab="roles" /> },
              { path: 'access/people/:userId', element: <AdminPersonAccessPage /> },
              { path: 'access/people/:userId/:projectId', element: <AdminPersonAccessPage /> },
              { path: 'profile', element: <AdminSettingsPage section="profile" /> },
              { path: 'profile/security', element: <AdminSettingsPage section="security" /> },
              { path: 'profile/notifications', element: <AdminSettingsPage section="notifications" /> },
              { path: 'profile/preferences', element: <AdminSettingsPage section="preferences" /> },
            ],
          },
        ],
      },
      // Staff app shell (clients are sent to their portal)
      {
        element: <StaffOnly />,
        children: [
      {
        element: <ByRole developer={<DeveloperLayout />} other={<AppLayout />} />,
        children: [
          { index: true, element: <RoleHome /> },

          // PM only
          {
            element: <RequireRole roles={['pm']} />,
            children: [{ path: 'dashboard', element: <DashboardPage /> }],
          },
          // Developer only
          {
            element: <RequireRole roles={['developer']} />,
            children: [{ path: 'my-work', element: <MyWorkPage /> }],
          },

          // Both roles (data is scoped by the backend)
          { path: 'projects', element: <ProjectsPage /> },
          // PM only: create and edit
          {
            element: <RequireRole roles={['pm']} />,
            children: [
              { path: 'projects/new', element: <ProjectCreatePage /> },
              { path: 'projects/:projectId/edit', element: <ProjectEditPage /> },
            ],
          },
          {
            path: 'projects/:projectId',
            element: <ByRole developer={<DevProjectLayout />} other={<ProjectLayout />} />,
            children: [
              { index: true, element: <ByRole developer={<DevOverviewPage />} other={<ProjectOverviewPage />} /> },
              { path: 'sprint-planning', element: <ByRole developer={<Navigate to="../board" replace />} other={<SprintPlanningPage />} /> },
              { path: 'board', element: <ByRole developer={<DevBoardPage />} other={<ProjectBoardPage />} /> },
              { path: 'requirements', element: <Navigate to="../change-requests" replace /> },
              { path: 'change-requests', element: <ProjectChangeRequestsPage /> },
              { path: 'change-requests/requirements/:requirementId', element: <RequirementDetailPage /> },
              { path: 'change-requests/:requestId', element: <ProjectChangeRequestPage /> },
              { path: 'reports', element: <ProjectReportsPage /> },
              { path: 'reports/:reportId', element: <ProjectReportPage /> },
              { path: 'list', element: <ByRole developer={<DevBacklogPage />} other={<ProjectListPage />} /> },
              { path: 'members', element: <ProjectMembersPage /> },
              { path: 'milestones', element: <MilestonesPage /> },
              { path: 'settings', element: <ProjectSettingsPage /> },
              { path: 'settings/people', element: <ProjectPeoplePage /> },
              { path: 'settings/people/:userId', element: <ProjectMemberPage /> },
            ],
          },
          { path: 'profile', element: <ByRole developer={<AdminSettingsPage section="profile" area="developer" />} other={<PmSettings><AmProfilePage /></PmSettings>} /> },
          { path: 'profile/security', element: <ByRole developer={<AdminSettingsPage section="security" area="developer" />} other={<PmSettings><AmSecurityPage /></PmSettings>} /> },
          { path: 'profile/notifications', element: <ByRole developer={<AdminSettingsPage section="notifications" area="developer" />} other={<PmSettings><AmNotificationsPage /></PmSettings>} /> },
          { path: 'profile/preferences', element: <ByRole developer={<AdminSettingsPage section="preferences" area="developer" />} other={<PmSettings><AmPreferencesPage /></PmSettings>} /> },
          { path: 'tasks', element: <TasksPage /> },
          { path: 'tasks/new', element: <TaskCreatePage /> },
          { path: 'tasks/:taskId', element: <TaskDetailPage /> },

          { path: 'forbidden', element: <ForbiddenPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
        ],
      },
    ],
  },
]);
