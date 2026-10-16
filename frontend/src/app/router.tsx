import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppLayout } from '@/layouts/AppLayout';
import { LoginPage } from '@/features/auth/LoginPage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { ProjectsPage } from '@/features/projects/ProjectsPage';
import { ProjectLayout } from '@/features/projects/ProjectLayout';
import { ProjectBoardPage, ProjectListPage, ProjectMembersPage } from '@/features/projects/ProjectViews';
import { MyWorkPage, TaskDetailPage, TasksPage } from '@/features/tasks/TaskPages';
import { ProfilePage } from '@/features/profile/ProfilePage';
import { ForbiddenPage, NotFoundPage } from '@/features/errors/ErrorPages';
import { RedirectIfAuthed, RequireAuth, RequireRole, RoleHome } from './guards';

export const router = createBrowserRouter([
  // Public
  {
    element: <RedirectIfAuthed />,
    children: [{ path: 'login', element: <LoginPage /> }],
  },

  // Authenticated app shell
  {
    element: <RequireAuth />,
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
          {
            path: 'projects/:projectId',
            element: <ProjectLayout />,
            children: [
              { index: true, element: <Navigate to="board" replace /> },
              { path: 'board', element: <ProjectBoardPage /> },
              { path: 'list', element: <ProjectListPage /> },
              { path: 'members', element: <ProjectMembersPage /> },
            ],
          },
          { path: 'profile', element: <ProfilePage /> },
          { path: 'tasks', element: <TasksPage /> },
          { path: 'tasks/:taskId', element: <TaskDetailPage /> },

          { path: 'forbidden', element: <ForbiddenPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);
