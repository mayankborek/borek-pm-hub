import { useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { ChangeRequestsView } from './ProjectChangeRequestsPage';
import { ChangeRequestView } from './ProjectChangeRequestPage';

/** Manager › project › Change requests: the same queue the Project Manager works from. */
export function ManagerChangeRequestsPage() {
  const { projectId = '' } = useParams();
  return <ChangeRequestsView projectId={projectId} requestPath={paths.managerChangeRequest} />;
}

export function ManagerChangeRequestPage() {
  const { projectId = '' } = useParams();
  return <ChangeRequestView projectId={projectId} listPath={paths.managerChangeRequests(projectId)} />;
}
