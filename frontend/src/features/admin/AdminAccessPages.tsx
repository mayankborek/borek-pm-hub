import { Fragment, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { ROLE_LABEL, useAdminUsers, type AdminUser } from './adminApi';
import {
  downloadAccessExport,
  usePersonProjectAccess,
  usePersonProjects,
  useResetRole,
  useResetSection,
  useRoleMatrix,
  useSetProjectControl,
  useSetRolePermission,
  type RoleCell,
  type RoleColumn,
  type Section,
} from './accessApi';
import { Back, Modal, Tabs, initials, usePopover } from './AdminUi';

const TONES = ['', 'g', 'y'] as const;
const roleName = (key: string) => (key === 'client' ? 'Client' : ROLE_LABEL[key] ?? key);

interface ProjectRef {
  id: string;
  name: string;
}

/** Pill colour per project: tint, mint, sand in the order the projects are listed. */
function useProjectTones(users: AdminUser[]) {
  return useMemo(() => {
    const all = new Map<string, ProjectRef>();
    // Projects keep the order the person with the most of them lists them in.
    for (const u of [...users].sort((a, b) => b.projects.length - a.projects.length))
      for (const p of u.projects) if (!all.has(p.id)) all.set(p.id, { id: p.id, name: p.name });
    const projects = [...all.values()];
    const tone = new Map(projects.map((p, i) => [p.id, TONES[i % TONES.length]]));
    return { projects, tone: (id: string) => tone.get(id) ?? '' };
  }, [users]);
}

export function AdminAccessPage({ tab }: { tab: 'people' | 'roles' }) {
  const { t } = usePrefs();
  return (
    <main className={`bf-content${tab === 'people' ? ' bf-pa' : ''}`} style={{ paddingTop: 24 }}>
      <h1>{t(tab === 'people' ? 'Person access' : 'Role permissions')}</h1>
      <p className="bf-sub">
        {t(tab === 'people' ? 'See who has access to each project and manage permissions for individual users.' : 'Configure which pages and actions are available to each role.')}
      </p>
      <div style={{ marginTop: -6 }}>
        <Tabs
          items={[
            { to: paths.adminAccess, label: 'Person access', on: tab === 'people' },
            { to: paths.adminRoles, label: 'Role permissions', on: tab === 'roles' },
          ]}
        />
      </div>
      {tab === 'people' ? <PersonAccess /> : <RolePermissions />}
    </main>
  );
}

// ---- Person access (person-access.html) -------------------------------------------------------------

function PersonAccess() {
  const { t } = usePrefs();
  const toast = useToast();
  const list = useAdminUsers('', '', 'active');
  const users = useMemo(() => (list.data?.items ?? []).filter((u) => u.role !== 'admin'), [list.data]);
  const { projects, tone } = useProjectTones(users);
  const [projectId, setProjectId] = useState('');
  const [q, setQ] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [personQ, setPersonQ] = useState('');
  const peopleMenu = usePopover();
  const exportMenu = usePopover();

  const inProject = users.filter((u) => !projectId || u.projects.some((p) => p.id === projectId));
  const rows = inProject.filter((u) => (!picked.length || picked.includes(u.id)) && (!q.trim() || u.name.toLowerCase().includes(q.trim().toLowerCase())));

  const choose = (id: string) => {
    setProjectId(id);
    setPicked([]);
    setPersonQ('');
    peopleMenu.setOpen(!!id);
  };

  /** The server builds the file from the same filters as the table. */
  const exportFile = (format: 'pdf' | 'csv') => {
    exportMenu.setOpen(false);
    downloadAccessExport({ q, projectId, personIds: picked }, format).catch((e) => toast.error(describeApiError(e, t('The export didn’t work. Try again.'))));
  };

  return (
    <>
      <div className="bf-head" style={{ marginBottom: 16 }}>
        <div className="bf-anchor" ref={peopleMenu.ref}>
          <div className="bf-seg" role="group" aria-label={t('Project')}>
            <button type="button" className={!projectId ? 'on' : undefined} aria-pressed={!projectId} onClick={() => choose('')}>{t('All projects')}</button>
            {projects.map((p) => (
              <button key={p.id} type="button" className={projectId === p.id ? 'on' : undefined} aria-pressed={projectId === p.id} onClick={() => choose(p.id)}>{p.name}</button>
            ))}
          </div>
          {peopleMenu.open && projectId && (
            <div className="bf-menu" role="menu" style={{ left: 0, top: 52, minWidth: 220 }}>
              <input className="bf-input" placeholder={t('Search by name')} aria-label={t('Search by name')} value={personQ} onChange={(e) => setPersonQ(e.target.value)} />
              {inProject
                .filter((u) => u.name.toLowerCase().includes(personQ.trim().toLowerCase()))
                .map((u) => (
                  <label key={u.id}>
                    <input type="checkbox" checked={picked.includes(u.id)} onChange={() => setPicked((p) => (p.includes(u.id) ? p.filter((x) => x !== u.id) : [...p, u.id]))} />
                    {u.name}
                  </label>
                ))}
              <button type="button" className="item" onClick={() => setPicked([])}>{t('Clear selection')}</button>
              <button type="button" className="item" onClick={() => peopleMenu.setOpen(false)}>{t('Done')}</button>
            </div>
          )}
        </div>
        <div className="bf-row">
          <input className="bf-input strong" style={{ width: 249 }} type="search" placeholder={`⌕  ${t('Search people')}`} aria-label={t('Search people')} value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="bf-anchor" ref={exportMenu.ref}>
            <button type="button" className="bf-btn" aria-label={t('Export')} aria-haspopup="menu" aria-expanded={exportMenu.open} onClick={() => exportMenu.setOpen((o) => !o)}>⋮</button>
            {exportMenu.open && (
              <div className="bf-menu" role="menu" style={{ right: 0, top: 40, minWidth: 196 }}>
                <button type="button" className="item" role="menuitem" onClick={() => exportFile('pdf')}>{t('Export as PDF')}</button>
                <button type="button" className="item" role="menuitem" onClick={() => exportFile('csv')}>{t('Export as CSV')}</button>
              </div>
            )}
          </div>
        </div>
      </div>

      <section className="bf-card bf-inset">
        {list.isError && (
          <p className="bf-error" role="alert" style={{ marginBottom: 10 }}>
            {describeApiError(list.error, t('We couldn’t load users'))}{' '}
            <button type="button" className="bf-link" onClick={() => list.refetch()}>{t('Retry')}</button>
          </p>
        )}
        <table className="bf-access" aria-busy={list.isFetching}>
          <thead>
            <tr>
              <th style={{ width: '15%' }}>{t('Person')}</th>
              <th style={{ width: '15%' }}>{t('Role')}</th>
              <th className="projects-col">{t('Projects they can access')}</th>
              <th className="c" style={{ width: '11%' }}>{t('Total')}</th>
              <th className="r" style={{ width: '12%' }}>{t('Action')}</th>
            </tr>
          </thead>
          <tbody>
            {list.isPending && <tr><td className="bf-empty" colSpan={5}>{t('Loading users')}</td></tr>}
            {list.data && !rows.length && <tr><td className="bf-empty" colSpan={5}>{t('No people match your search.')}</td></tr>}
            {rows.map((u) => (
              <tr key={u.id}>
                <td><b>{u.name}</b></td>
                <td>{t(roleName(u.role))}</td>
                <td>{u.projects.length ? u.projects.map((p) => <span key={p.id} className={`bf-pill ${tone(p.id)}`}>{p.name}</span>) : <span className="bf-muted">–</span>}</td>
                <td className="c">{u.projects.length}</td>
                <td className="r">
                  {u.role === 'client' ? <span className="bf-muted">—</span> : <Link className="bf-btn" to={paths.adminAccessPerson(u.id)}>{t('Manage')}</Link>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

// ---- Role permissions (role-permissions.html) --------------------------------------------------------

const GROUP_TONES = ['', 'g', 'y'] as const;
const ROLE_NAMES: Record<string, string> = {
  manager: 'Manager',
  pm: 'Project Manager',
  account_manager: 'Account Manager',
  developer: 'Developer',
  admin: 'Administrator',
  client: 'Client',
};
const nameOf = (r: RoleColumn) => ROLE_NAMES[r.role] ?? r.label;

/** The matrix rows, grouped by section in the order the server lists them. */
function groupRows(roles: RoleColumn[]) {
  const groups: { section: string; cells: RoleCell[] }[] = [];
  for (const cell of roles[0]?.permissions ?? []) {
    const last = groups[groups.length - 1];
    if (last?.section === cell.section) last.cells.push(cell);
    else groups.push({ section: cell.section, cells: [cell] });
  }
  return groups;
}

function RolePermissions() {
  const { t } = usePrefs();
  const toast = useToast();
  const matrix = useRoleMatrix();
  const setPermission = useSetRolePermission();
  const reset = useResetRole();
  const [saved, setSaved] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const menu = usePopover();
  const roles = matrix.data?.roles ?? [];
  const fail = (e: unknown) => toast.error(describeApiError(e, t('That didn’t work. Try again.')));

  return (
    <>
      {matrix.isError && (
        <p className="bf-error" role="alert" style={{ marginBottom: 10 }}>
          {describeApiError(matrix.error, t('We couldn’t load role permissions'))}{' '}
          <button type="button" className="bf-link" onClick={() => matrix.refetch()}>{t('Retry')}</button>
        </p>
      )}
      <section className="bf-card bf-inset" style={{ marginTop: -1 }}>
        <table className="bf-perm" aria-busy={matrix.isFetching}>
          <thead>
            <tr>
              <th>{t('Permission')}</th>
              {roles.map((r) => (
                <th key={r.role}>
                  {t(nameOf(r))}
                  <span className="bf-anchor" ref={open === r.role ? menu.ref : undefined}>
                    <button type="button" className="bf-kebab" aria-label={t('{role} options', { role: t(nameOf(r)) })} aria-haspopup="menu" aria-expanded={open === r.role && menu.open} onClick={() => { setOpen(r.role); menu.setOpen(open !== r.role || !menu.open); }}>⋮</button>
                    {open === r.role && menu.open && (
                      <RoleMenu
                        role={r}
                        right={r.role === 'client' || r.role === 'admin'}
                        busy={reset.isPending}
                        onReset={() => reset.mutate(r.role, { onSuccess: () => { menu.setOpen(false); setSaved(true); }, onError: fail })}
                      />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.isPending && <tr><td className="bf-empty" colSpan={7}>{t('Loading…')}</td></tr>}
            {groupRows(roles).map((g, gi) => (
              <Fragment key={g.section}>
                <tr className={`group ${GROUP_TONES[gi % GROUP_TONES.length]}`}><td colSpan={roles.length + 1}>{t(g.section)}</td></tr>
                {g.cells.map((row) => (
                  <tr key={row.key}>
                    <td>{t(row.label)}</td>
                    {roles.map((r) => {
                      const cell = r.permissions.find((c) => c.key === row.key);
                      return cell ? (
                        <PermissionCell
                          key={r.role}
                          cell={cell}
                          role={r}
                          busy={setPermission.isPending}
                          onChange={(enabled) => setPermission.mutate({ role: r.role, permission: cell.key, enabled }, { onSuccess: () => setSaved(true), onError: fail })}
                        />
                      ) : (
                        <td key={r.role}>—</td>
                      );
                    })}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </section>
      {saved && (
        <Modal title="Role access saved" width={480} onClose={() => setSaved(false)}>
          <p className="bf-muted" style={{ margin: '10px 0 14px' }}>{t('Changes apply to users of these roles on their next request.')}</p>
          <button type="button" className="bf-btn primary" onClick={() => setSaved(false)}>{t('Done')}</button>
        </Modal>
      )}
    </>
  );
}

function RoleMenu({ role, right, busy, onReset }: { role: RoleColumn; right: boolean; busy: boolean; onReset: () => void }) {
  const { t } = usePrefs();
  const style = right ? { right: 0, top: 28, textAlign: 'left' as const, fontWeight: 500 } : { left: -60, top: 28, textAlign: 'left' as const, fontWeight: 500 };
  if (!role.editable) {
    return (
      <div className="bf-menu" role="menu" style={style}>
        <a className="off" role="menuitem" aria-disabled="true">{t('Reset to default')}</a>
        <p className="note">{t('This role has fixed permissions.')}</p>
      </div>
    );
  }
  return (
    <div className="bf-menu" role="menu" style={style}>
      <button type="button" className="item" role="menuitem" disabled={busy || !role.customised} onClick={onReset}>{t('Reset to default')}</button>
    </div>
  );
}

function PermissionCell({ cell, role, busy, onChange }: { cell: RoleCell; role: RoleColumn; busy: boolean; onChange: (enabled: boolean) => void }) {
  const { t } = usePrefs();
  if (cell.value === 'none') return <td>—</td>;
  if (cell.value === 'always') return <td>{t('Always')}</td>;
  return (
    <td>
      <input
        type="checkbox"
        className="bf-sw"
        checked={cell.value === 'on'}
        disabled={!cell.editable || busy}
        aria-label={`${t(cell.label)}: ${t(nameOf(role))}`}
        onChange={(e) => onChange(e.target.checked)}
      />
    </td>
  );
}

// ---- Manage access (access-*.html) -------------------------------------------------------------------

export function AdminPersonAccessPage() {
  const { t } = usePrefs();
  const { userId = '', projectId = '' } = useParams();
  const list = useAdminUsers('', '', 'all');
  const projects = usePersonProjects(userId);
  const user = (list.data?.items ?? []).find((u) => u.id === userId);

  if (!user) {
    return (
      <main className="bf-content">
        <Back to={paths.adminAccess} />
        <h2>{t(list.isPending ? 'Loading users' : 'User not found')}</h2>
      </main>
    );
  }

  const items = projects.data?.items ?? [];
  const project = items.find((p) => p.id === projectId);

  return (
    <main className="bf-content">
      <Back to={paths.adminAccess} />
      <div className="bf-hero">
        <i>{initials(user.name)}</i>
        <div>
          <h2>{user.name}</h2>
          <span className="bf-muted" style={{ fontSize: 12 }}>{t(roleName(user.role))}</span>
        </div>
      </div>
      <div className="bf-seg">
        <Link className={!project ? 'on' : undefined} to={paths.adminAccessPerson(user.id)}>{t('All')}</Link>
        {items.map((p) => (
          <Link key={p.id} className={project?.id === p.id ? 'on' : undefined} to={paths.adminAccessProject(user.id, p.id)}>{p.name}</Link>
        ))}
      </div>
      {projects.isError && (
        <p className="bf-error" role="alert" style={{ marginTop: 16 }}>
          {describeApiError(projects.error, t('We couldn’t load this person’s projects'))}{' '}
          <button type="button" className="bf-link" onClick={() => projects.refetch()}>{t('Retry')}</button>
        </p>
      )}
      {project ? (
        <ProjectPermissions userId={user.id} projectId={project.id} editable={projects.data?.editable ?? false} />
      ) : (
        <>
          <h3 style={{ fontSize: 18, margin: '37px 0 12px' }}>{t('Projects')}</h3>
          {projects.isPending && <p className="bf-muted">{t('Loading…')}</p>}
          {projects.data && !items.length && <p className="bf-muted">{t('This person is not on any project yet.')}</p>}
          {items.map((p) => (
            <div className="bf-proj" key={p.id}>
              <b>{p.name}</b>
              <Link to={paths.adminAccessProject(user.id, p.id)} style={{ fontWeight: 500 }}>{t('Manage permissions')}</Link>
            </div>
          ))}
        </>
      )}
    </main>
  );
}

function ProjectPermissions({ userId, projectId, editable }: { userId: string; projectId: string; editable: boolean }) {
  const { t } = usePrefs();
  const access = usePersonProjectAccess(userId, projectId);
  const [step, setStep] = useState(0);
  const sections = access.data?.sections ?? [];
  const section = sections[Math.min(step, sections.length - 1)];

  if (access.isError) {
    return (
      <p className="bf-error" role="alert" style={{ marginTop: 16 }}>
        {describeApiError(access.error, t('We couldn’t load this person’s access'))}{' '}
        <button type="button" className="bf-link" onClick={() => access.refetch()}>{t('Retry')}</button>
      </p>
    );
  }
  if (!section) return <p className="bf-muted" style={{ marginTop: 16 }}>{t('Loading…')}</p>;

  return (
    <div className="bf-split">
      <nav className="bf-card bf-steps" aria-label={t('Permission sections')}>
        {sections.map((s, i) => (
          <button key={s.key} type="button" className={s === section ? 'on' : undefined} aria-current={s === section ? 'true' : undefined} onClick={() => setStep(i)}>
            {t(s.label)}
          </button>
        ))}
      </nav>
      <SectionPanel key={`${projectId}:${section.key}`} userId={userId} projectId={projectId} section={section} editable={editable} />
    </div>
  );
}

function SectionPanel({ userId, projectId, section, editable }: { userId: string; projectId: string; section: Section; editable: boolean }) {
  const { t } = usePrefs();
  const toast = useToast();
  const setControl = useSetProjectControl(userId, projectId);
  const reset = useResetSection(userId, projectId);
  const fail = (e: unknown) => toast.error(describeApiError(e, t('That didn’t work. Try again.')));
  return (
    <section className="bf-card bf-panel">
      <header>
        <h3>{t(section.label)}</h3>
        <button type="button" disabled={!editable || !section.customised || reset.isPending} onClick={() => reset.mutate(section.key, { onError: fail })}>{t('Reset to default')}</button>
      </header>
      {section.controls.map((c) => (
        <label key={c.key}>
          {t(c.label)}
          <input
            type="checkbox"
            className="bf-sw"
            checked={c.enabled}
            disabled={!editable || !c.editable || setControl.isPending}
            onChange={(e) => setControl.mutate({ permission: c.key, enabled: e.target.checked }, { onError: fail })}
          />
        </label>
      ))}
    </section>
  );
}
