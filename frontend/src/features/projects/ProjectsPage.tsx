import { Link } from 'react-router-dom';
import { paths } from '@/app/routes';
import { PagePlaceholder } from '@/shared/ui/PagePlaceholder';

export function ProjectsPage() {
  return (
    <PagePlaceholder title="Projects" description="Projects you can access.">
      <p>
        <Link to={paths.projectBoard('demo')}>Open demo project</Link>
      </p>
    </PagePlaceholder>
  );
}
