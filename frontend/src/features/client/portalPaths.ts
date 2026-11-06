import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';

/** URLs of the shared portal pages. Clients and Account Managers see the same screens under their own prefix. */
export function usePortalPaths() {
  const am = useAuth().user?.role === 'account_manager';
  return am
    ? {
        home: paths.amHome,
        profile: paths.amProfile,
        projects: paths.amProjects,
        project: paths.amProject,
        milestones: paths.amMilestones,
        reports: paths.amReports,
        report: paths.amReport,
        // Account Managers have no change request tab: the project overview summarises them.
        changeRequests: paths.amProject,
        people: paths.amStakeholders,
      }
    : {
        home: paths.clientHome,
        profile: paths.clientProfile,
        projects: paths.clientProjects,
        project: paths.clientProject,
        milestones: paths.clientMilestones,
        reports: paths.clientReports,
        report: paths.clientReport,
        changeRequests: paths.clientChangeRequests,
        people: paths.clientContacts,
      };
}
