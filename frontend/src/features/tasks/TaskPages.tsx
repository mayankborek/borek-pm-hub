import { useParams } from 'react-router-dom';
import { PagePlaceholder } from '@/shared/ui/PagePlaceholder';

export const MyWorkPage = () => (
  <PagePlaceholder title="My Work" description="Tasks assigned to you across projects." />
);

export const TasksPage = () => (
  <PagePlaceholder title="All Tasks" description="Tasks across every project you can access." />
);

export function TaskDetailPage() {
  const { taskId } = useParams();
  return <PagePlaceholder title={`Task ${taskId}`} description="Task detail, status and assignee." />;
}
