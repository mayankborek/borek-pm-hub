import { PagePlaceholder } from '@/shared/ui/PagePlaceholder';

export const ProjectBoardPage = () => (
  <PagePlaceholder title="Board" description="Tasks grouped by status (GET /projects/{id}/tasks?view=board)." />
);

export const ProjectListPage = () => (
  <PagePlaceholder title="List" description="Filterable, paginated task list." />
);

export const ProjectMembersPage = () => (
  <PagePlaceholder title="Members" description="Project members and their roles." />
);
