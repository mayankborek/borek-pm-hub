import { paths } from '@/app/routes';
import { useAuth } from '@/features/auth/AuthContext';

/** URLs of the shared portal pages. Clients, Account Managers and Managers see the same screens under their own prefix. */
export function usePortalPaths() {
  const role = useAuth().user?.role;
  if (role === 'manager') {
    return {
      home: paths.managerHome,
      profile: paths.managerProfile,
      projects: paths.managerProjects,
      project: paths.managerProject,
      milestones: paths.managerMilestones,
      reports: paths.managerReports,
      report: paths.managerReport,
      changeRequests: paths.managerChangeRequests,
      people: paths.managerStakeholders,
    };
  }
  const am = role === 'account_manager';
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
