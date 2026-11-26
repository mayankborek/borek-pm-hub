import { useSyncExternalStore } from 'react';

/**
 * Role permissions, per-person project access and the organisation details the API has no fields for
 * live in this browser's localStorage until the endpoints exist. Swap `read`/`commit` for API calls then;
 * the hooks and shapes below are what the pages depend on.
 */

// ---- Role permissions (role-permissions.html) ------------------------------------------------------

export interface RoleColumn {
  id: string;
  name: string;
  /** The backend's global role, used to count users. */
  key: string;
  /** Fixed roles have nothing to reset. */
  fixed?: boolean;
}

/** Column order of the permissions table. */
export const ROLES: RoleColumn[] = [
  { id: 'manager', name: 'Manager', key: 'manager' },
  { id: 'project-manager', name: 'Project Manager', key: 'pm' },
  { id: 'account-manager', name: 'Account Manager', key: 'account_manager' },
  { id: 'developer', name: 'Developer', key: 'developer' },
  { id: 'administrator', name: 'Administrator', key: 'admin', fixed: true },
  { id: 'client', name: 'Client', key: 'client', fixed: true },
];

/** `always`: cannot be switched off. `na`: does not apply to the role. */
export type Cell = 'always' | 'on' | 'off' | 'na';

export interface PermissionRow {
  id: string;
  label: string;
  /** Default per role, in ROLES order. */
  cells: [Cell, Cell, Cell, Cell, Cell, Cell];
}

export interface PermissionGroup {
  id: string;
  label: string;
  tone: '' | 'g' | 'y';
  rows: PermissionRow[];
}

export const PERMISSION_GROUPS: PermissionGroup[] = [
  {
    id: 'navigation',
    label: 'Workspace navigation',
    tone: '',
    rows: [
      { id: 'dashboard', label: 'Dashboard', cells: ['always', 'always', 'always', 'always', 'na', 'always'] },
      { id: 'their-projects', label: 'Their projects', cells: ['always', 'always', 'always', 'always', 'na', 'always'] },
      { id: 'my-tasks', label: 'My tasks', cells: ['off', 'on', 'on', 'on', 'na', 'na'] },
      { id: 'projects-menu', label: 'Projects menu', cells: ['on', 'on', 'on', 'off', 'na', 'na'] },
    ],
  },
  {
    id: 'team',
    label: 'Team visibility',
    tone: 'g',
    rows: [
      { id: 'team-capacity', label: 'Team capacity', cells: ['on', 'na', 'na', 'na', 'na', 'na'] },
      { id: 'team-workload', label: 'Team workload', cells: ['on', 'na', 'na', 'na', 'na', 'na'] },
    ],
  },
  {
    id: 'actions',
    label: 'Project actions',
    tone: 'y',
    rows: [
      { id: 'create-projects', label: 'Create projects', cells: ['on', 'on', 'na', 'na', 'na', 'na'] },
      { id: 'manage-members', label: 'Manage project members', cells: ['on', 'on', 'na', 'na', 'na', 'na'] },
      { id: 'set-status', label: 'Set project status', cells: ['on', 'on', 'na', 'na', 'na', 'na'] },
    ],
  },
];

export const defaultCell = (row: PermissionRow, roleId: string): Cell => row.cells[ROLES.findIndex((r) => r.id === roleId)] ?? 'na';

// ---- Project access per person (access-*.html) -----------------------------------------------------

export interface AccessSwitch {
  id: string;
  label: string;
  /** Global roles that have it by default. */
  on: string[];
}

export interface AccessSection {
  id: string;
  label: string;
  switches: AccessSwitch[];
}

const ALL = ['pm', 'manager', 'account_manager', 'developer'];
const LEADS = ['pm', 'manager'];
const NOT_DEV = ['pm', 'manager', 'account_manager'];

export const ACCESS_SECTIONS: AccessSection[] = [
  {
    id: 'overview',
    label: 'Project overview',
    switches: [
      { id: 'overview-view', label: 'View project page', on: ALL },
      { id: 'overview-edit', label: 'Edit project details', on: LEADS },
      { id: 'overview-status', label: 'Change project status', on: NOT_DEV },
      { id: 'overview-phases', label: 'Manage project phases', on: LEADS },
      { id: 'overview-close', label: 'Close or reopen project', on: LEADS },
    ],
  },
  {
    id: 'tasks',
    label: 'Tasks and board',
    switches: [
      { id: 'tasks-view', label: 'View tasks and board', on: ALL },
      { id: 'tasks-create', label: 'Create tasks', on: ['pm', 'manager', 'developer'] },
      { id: 'tasks-edit', label: 'Edit tasks', on: ['pm', 'manager', 'developer'] },
      { id: 'tasks-assign', label: 'Assign tasks', on: LEADS },
      { id: 'tasks-delete', label: 'Delete tasks', on: LEADS },
    ],
  },
  {
    id: 'sprints',
    label: 'Sprints and milestones',
    switches: [
      { id: 'sprints-view', label: 'View sprints and milestones', on: ALL },
      { id: 'sprints-sprints', label: 'Manage sprints', on: LEADS },
      { id: 'sprints-milestones', label: 'Manage milestones', on: NOT_DEV },
    ],
  },
  {
    id: 'changes',
    label: 'Change requests',
    switches: [
      { id: 'changes-view', label: 'View change requests', on: ALL },
      { id: 'changes-submit', label: 'Submit change requests', on: NOT_DEV },
      { id: 'changes-decide', label: 'Approve or reject change requests', on: LEADS },
    ],
  },
  {
    id: 'people',
    label: 'People and access',
    switches: [
      { id: 'people-view', label: 'View project members', on: ALL },
      { id: 'people-manage', label: 'Manage project members', on: LEADS },
      { id: 'people-invite', label: 'Invite client contacts', on: NOT_DEV },
    ],
  },
  {
    id: 'reports',
    label: 'Reports and project status',
    switches: [
      { id: 'reports-view', label: 'View reports', on: ALL },
      { id: 'reports-edit', label: 'Create and edit reports', on: NOT_DEV },
      { id: 'reports-publish', label: 'Publish reports to the client', on: NOT_DEV },
    ],
  },
];

const defaultAccess = (switchDef: AccessSwitch, role: string) => switchDef.on.includes(role);

// ---- Organisation details the API does not store yet -----------------------------------------------

export interface OrgExtras {
  industry: string;
  website: string;
  primaryEmail: string;
  projectManagerId: string;
}

export const EMPTY_EXTRAS: OrgExtras = { industry: '', website: '', primaryEmail: '', projectManagerId: '' };

// ---- Store -----------------------------------------------------------------------------------------

interface State {
  /** `${roleId}:${rowId}` -> switched on? Only deviations from the default. */
  roles: Record<string, boolean>;
  /** `${userId}:${projectId}:${switchId}` -> switched on? Only deviations from the default. */
  access: Record<string, boolean>;
  orgs: Record<string, OrgExtras>;
  /** Preference, not account data: whether the notification topics are on. */
  topics: Record<string, boolean>;
  /** The administrator's own phone number: there is no endpoint for it yet. */
  phone: string;
}

const KEY = 'borek.admin-console.v2';
const SEED: State = { roles: {}, access: {}, orgs: {}, topics: {}, phone: '' };

function read(): State {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...SEED, ...(JSON.parse(raw) as Partial<State>) };
  } catch {
    /* storage unavailable or corrupt: start from the seed */
  }
  return SEED;
}

let state = read();
const listeners = new Set<() => void>();

function commit(next: State) {
  state = next;
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* the change still applies for this page view */
  }
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
};
const useStore = () => useSyncExternalStore(subscribe, () => state);

/** The state of one switchable cell of the permissions table. */
export function useRoleCell(row: PermissionRow, roleId: string): Cell {
  const stored = useStore().roles[`${roleId}:${row.id}`];
  const base = defaultCell(row, roleId);
  return base === 'on' || base === 'off' ? (stored === undefined ? base : stored ? 'on' : 'off') : base;
}

export const roleActions = {
  set(roleId: string, rowId: string, on: boolean, defaultOn: boolean) {
    const roles = { ...state.roles };
    if (on === defaultOn) delete roles[`${roleId}:${rowId}`];
    else roles[`${roleId}:${rowId}`] = on;
    commit({ ...state, roles });
  },
  reset(roleId: string) {
    const roles = Object.fromEntries(Object.entries(state.roles).filter(([k]) => !k.startsWith(`${roleId}:`)));
    commit({ ...state, roles });
  },
};

export function useAccessSwitch(userId: string, projectId: string, def: AccessSwitch, role: string): boolean {
  const stored = useStore().access[`${userId}:${projectId}:${def.id}`];
  return stored ?? defaultAccess(def, role);
}

export const accessActions = {
  set(userId: string, projectId: string, def: AccessSwitch, role: string, on: boolean) {
    const access = { ...state.access };
    if (on === defaultAccess(def, role)) delete access[`${userId}:${projectId}:${def.id}`];
    else access[`${userId}:${projectId}:${def.id}`] = on;
    commit({ ...state, access });
  },
  reset(userId: string, projectId: string, section: AccessSection) {
    const ids = new Set(section.switches.map((s) => `${userId}:${projectId}:${s.id}`));
    commit({ ...state, access: Object.fromEntries(Object.entries(state.access).filter(([k]) => !ids.has(k))) });
  },
};

export const useOrgExtras = (orgId: string): OrgExtras => useStore().orgs[orgId] ?? EMPTY_EXTRAS;

export const orgActions = {
  set(orgId: string, extras: OrgExtras) {
    commit({ ...state, orgs: { ...state.orgs, [orgId]: extras } });
  },
};

export const useTopic = (id: string): boolean => useStore().topics[id] ?? true;

export const topicActions = {
  set(id: string, on: boolean) {
    commit({ ...state, topics: { ...state.topics, [id]: on } });
  },
};

export const usePhone = (): string => useStore().phone;

export const profileActions = {
  setPhone(phone: string) {
    commit({ ...state, phone });
  },
};
