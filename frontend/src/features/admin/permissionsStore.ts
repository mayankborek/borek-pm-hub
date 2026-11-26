import { useSyncExternalStore } from 'react';

/**
 * Role access has no backend yet, so it lives in this browser's localStorage. Swap `read`/`commit`
 * for API calls when the endpoints exist; the hooks and the shapes below are what the pages depend on.
 */
export type Access = 'view' | 'edit' | 'denied';

export const AREAS = [
  { id: 'projects', label: 'Projects', includes: 'Project details, health and progress' },
  { id: 'tasks', label: 'Tasks', includes: 'Tasks, assignments, status, comments and files' },
  { id: 'milestones', label: 'Milestones', includes: 'Milestone dates, progress and linked work' },
  { id: 'change-requests', label: 'Change requests', includes: 'Submitted changes, attachments and request status' },
  { id: 'reports', label: 'Reports', includes: 'Project reports, drafts and publication' },
  { id: 'stakeholders', label: 'Stakeholders', includes: 'Stakeholder names, responsibilities and contacts' },
  { id: 'access', label: 'Access', includes: 'Project members, invitations and client access' },
  { id: 'administration', label: 'Administration', includes: 'User accounts, roles and platform configuration' },
] as const;

export type AreaId = (typeof AREAS)[number]['id'];
export type Permissions = Record<AreaId, Access>;

export interface AdminRole {
  id: string;
  name: string;
  /** The backend's global role, used to count users. */
  key: string;
}

export const ROLES: AdminRole[] = [
  { id: 'administrator', name: 'Administrator', key: 'admin' },
  { id: 'manager', name: 'Manager', key: 'manager' },
  { id: 'project-manager', name: 'Project Manager', key: 'pm' },
  { id: 'developer', name: 'Developer', key: 'developer' },
  { id: 'account-manager', name: 'Account Manager', key: 'account_manager' },
  { id: 'client', name: 'Client', key: 'client' },
];

const grid = (...v: Access[]): Permissions => Object.fromEntries(AREAS.map((a, i) => [a.id, v[i]])) as Permissions;

/** Column order: projects, tasks, milestones, change requests, reports, stakeholders, access, administration. */
export const DEFAULT_PERMISSIONS: Record<string, Permissions> = {
  administrator: grid('denied', 'denied', 'denied', 'denied', 'denied', 'denied', 'denied', 'edit'),
  manager: grid('edit', 'edit', 'edit', 'edit', 'edit', 'edit', 'edit', 'denied'),
  'project-manager': grid('edit', 'edit', 'edit', 'edit', 'edit', 'edit', 'edit', 'denied'),
  developer: grid('view', 'edit', 'view', 'view', 'view', 'view', 'denied', 'denied'),
  'account-manager': grid('view', 'view', 'view', 'edit', 'edit', 'edit', 'edit', 'denied'),
  client: grid('view', 'denied', 'view', 'edit', 'view', 'view', 'denied', 'denied'),
};

interface State {
  permissions: Record<string, Permissions>;
}

const KEY = 'borek.admin-console';
const SEED: State = { permissions: {} };

function read(): State {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const s = JSON.parse(raw) as Partial<State>;
      if (s.permissions) return { permissions: s.permissions };
    }
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

export const usePermissions = (roleId: string): Permissions =>
  useStore().permissions[roleId] ?? DEFAULT_PERMISSIONS[roleId] ?? grid(...AREAS.map((): Access => 'denied'));

export const permissionActions = {
  set(roleId: string, area: AreaId, access: Access) {
    const current = state.permissions[roleId] ?? DEFAULT_PERMISSIONS[roleId];
    commit({ ...state, permissions: { ...state.permissions, [roleId]: { ...current, [area]: access } } });
  },
  reset(roleId: string) {
    const rest = { ...state.permissions };
    delete rest[roleId];
    commit({ ...state, permissions: rest });
  },
};

export const isCustomised = (roleId: string, p: Permissions) => AREAS.some((a) => p[a.id] !== DEFAULT_PERMISSIONS[roleId]?.[a.id]);
