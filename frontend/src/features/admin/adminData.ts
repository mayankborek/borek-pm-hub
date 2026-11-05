/** Sample directory data from the design. No admin API exists yet; swap these for queries when the backend lands. */
export interface AdminUser {
  id: string;
  name: string;
  email: string;
  role: string;
  projects: string[];
  status: 'Active' | 'Inactive';
  /** Staff names link to a detail page in the design; client contacts do not. */
  linked: boolean;
}

export interface AdminOrganisation {
  id: string;
  name: string;
  accountManager: string;
  status: 'Active' | 'Inactive';
}

export interface AdminRole {
  id: string;
  name: string;
  users: number;
}

export const ADMIN_USERS: AdminUser[] = [
  { id: 'u1', name: 'Alex Morgan', email: 'alex.morgan@boreksolutions.com', role: 'Project Manager', projects: ['Website Redesign', 'Customer portal'], status: 'Active', linked: true },
  { id: 'u2', name: 'Noah Patel', email: 'noah.patel@boreksolutions.com', role: 'Developer', projects: ['Website Redesign'], status: 'Active', linked: true },
  { id: 'u3', name: 'Jordan Lee', email: 'jordan.lee@customer.com', role: 'Client contact', projects: ['Website Redesign'], status: 'Active', linked: false },
];

export const ADMIN_ORGANISATIONS: AdminOrganisation[] = [
  { id: 'o1', name: 'Customer organisation', accountManager: 'Morgan Ellis', status: 'Active' },
];

export const ADMIN_ROLES: AdminRole[] = [
  { id: 'administrator', name: 'Administrator', users: 1 },
  { id: 'project-manager', name: 'Project Manager', users: 1 },
  { id: 'developer', name: 'Developer', users: 1 },
  { id: 'account-manager', name: 'Account Manager', users: 1 },
  { id: 'client', name: 'Client', users: 1 },
];
