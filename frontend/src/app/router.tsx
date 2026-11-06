import { createBrowserRouter, Navigate } from 'react-router-dom';
import { paths } from './routes';
import { AppLayout } from '@/layouts/AppLayout';
import { LoginPage } from '@/features/auth/LoginPage';
import { SetPasswordPage } from '@/features/auth/SetPasswordPage';
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
import { ClientMilestonesPage } from '@/features/client/ClientMilestonesPage';
import { ClientContactsPage } from '@/features/client/ClientContactsPage';
import { ClientProfilePage } from '@/features/client/ClientProfilePage';
import { ClientPlaceholderPage, ClientReportPage, ClientReportsPage } from '@/features/client/ClientReportsPages';
import { AdminLayout } from '@/features/admin/AdminLayout';
import { AdminUsersPage } from '@/features/admin/AdminUsersPage';
import { AdminUserPage } from '@/features/admin/AdminUserPage';
import { AdminInvitationPage } from '@/features/admin/AdminInvitationPage';
import { AdminOrganisationsPage } from '@/features/admin/AdminOrganisationsPage';
import { AdminOrganisationPage } from '@/features/admin/AdminOrganisationPage';
import { AdminRolesPage } from '@/features/admin/AdminRolesPage';
import { AdminRolePage } from '@/features/admin/AdminRolePage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { ProjectsPage } from '@/features/projects/ProjectsPage';
import { ProjectLayout } from '@/features/projects/ProjectLayout';
import { ProjectCreatePage, ProjectEditPage } from '@/features/projects/ProjectFormPage';
import { ProjectOverviewPage } from '@/features/projects/ProjectOverviewPage';
import { ProjectBoardPage } from '@/features/projects/ProjectBoardPage';
import { ProjectListPage, ProjectMembersPage } from '@/features/projects/ProjectViews';
import { TasksPage } from '@/features/tasks/TaskPages';
import { TaskCreatePage } from '@/features/tasks/TaskCreatePage';
import { MyWorkPage } from '@/features/tasks/MyWorkPage';
import { TaskDetailPage } from '@/features/tasks/TaskDetailPage';
import { ProfilePage } from '@/features/profile/ProfilePage';
import { ForbiddenPage, NotFoundPage } from '@/features/errors/ErrorPages';
import { RedirectIfAuthed, RequireAuth, RequireRole, RoleHome, StaffOnly } from './guards';

export const router = createBrowserRouter([
  // Public, reachable even while signed in (an administrator may open a link in their own browser)
  { path: 'set-password', element: <SetPasswordPage /> },

  // Public
  {
    element: <RedirectIfAuthed />,
    children: [
      { path: 'login', element: <LoginPage /> },
      { path: 'client/login', element: <ClientLoginPage /> },
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
              { path: 'profile', element: <ClientProfilePage /> },
              { path: 'projects', element: <ClientProjectsPage /> },
              {
                path: 'projects/:projectId',
                element: <ClientProjectLayout />,
                children: [
                  { index: true, element: <ClientOverviewPage /> },
                  { path: 'milestones', element: <ClientMilestonesPage /> },
                  { path: 'reports', element: <ClientReportsPage /> },
                  { path: 'reports/:reportId', element: <ClientReportPage /> },
                  { path: 'change-requests', element: <ClientPlaceholderPage /> },
                  { path: 'contacts', element: <ClientContactsPage /> },
                ],
              },
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
              { path: 'users/:userId', element: <AdminUserPage /> },
              { path: 'users/:userId/invitation', element: <AdminInvitationPage /> },
              { path: 'organisations', element: <AdminOrganisationsPage /> },
              { path: 'organisations/:orgId', element: <AdminOrganisationPage /> },
              { path: 'roles', element: <AdminRolesPage /> },
              { path: 'roles/:roleId', element: <AdminRolePage /> },
              { path: 'profile', element: <ProfilePage /> },
            ],
          },
        ],
      },
      // Staff app shell (clients are sent to their portal)
      {
        element: <StaffOnly />,
        children: [
      {
        element: <AppLayout />,
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
            element: <ProjectLayout />,
            children: [
              { index: true, element: <ProjectOverviewPage /> },
              { path: 'board', element: <ProjectBoardPage /> },
              { path: 'list', element: <ProjectListPage /> },
              { path: 'members', element: <ProjectMembersPage /> },
            ],
          },
          { path: 'profile', element: <ProfilePage /> },
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
