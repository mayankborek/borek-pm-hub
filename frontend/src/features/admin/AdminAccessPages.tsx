import { Fragment, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { ROLE_LABEL, useAdminUsers, type AdminUser } from './adminApi';
import {
  ACCESS_SECTIONS,
  PERMISSION_GROUPS,
  ROLES,
  accessActions,
  defaultCell,
  roleActions,
  useAccessSwitch,
  useRoleCell,
  type AccessSection,
  type PermissionRow,
  type RoleColumn,
} from './adminStore';
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
    <main className="bf-content" style={{ paddingTop: 24 }}>
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

  const exportCsv = () => {
    const cell = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
    const lines = [['Person', 'Role', 'Projects', 'Total'].map(cell).join(',')];
    for (const u of rows) lines.push([u.name, t(roleName(u.role)), u.projects.map((p) => p.name).join('; '), u.projects.length].map(cell).join(','));
    const url = URL.createObjectURL(new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'person-access.csv';
    a.click();
    URL.revokeObjectURL(url);
    exportMenu.setOpen(false);
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
          <input className="bf-input strong" style={{ width: 218 }} type="search" placeholder={`⌕  ${t('Search people')}`} aria-label={t('Search people')} value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="bf-anchor" ref={exportMenu.ref}>
            <button type="button" className="bf-btn" aria-label={t('Export')} aria-haspopup="menu" aria-expanded={exportMenu.open} onClick={() => exportMenu.setOpen((o) => !o)}>⋮</button>
            {exportMenu.open && (
              <div className="bf-menu" role="menu" style={{ right: 0, top: 40, minWidth: 196 }}>
                <button type="button" className="item" role="menuitem" onClick={() => { exportMenu.setOpen(false); window.print(); }}>{t('Export as PDF')}</button>
                <button type="button" className="item" role="menuitem" onClick={exportCsv}>{t('Export as CSV')}</button>
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
              <th>{t('Projects they can access')}</th>
              <th className="c" style={{ width: '8%' }}>{t('Total')}</th>
              <th className="r" style={{ width: '13%' }}>{t('Action')}</th>
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

function RolePermissions() {
  const { t } = usePrefs();
  const [saved, setSaved] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const menu = usePopover();
  const colspan = ROLES.length + 1;

  return (
    <>
      <section className="bf-card bf-inset" style={{ marginTop: -1 }}>
        <table className="bf-perm">
          <thead>
            <tr>
              <th>{t('Permission')}</th>
              {ROLES.map((r) => (
                <th key={r.id}>
                  {t(r.name)}
                  <span className="bf-anchor" ref={open === r.id ? menu.ref : undefined}>
                    <button type="button" className="bf-kebab" aria-label={t('{role} options', { role: t(r.name) })} aria-haspopup="menu" aria-expanded={open === r.id && menu.open} onClick={() => { setOpen(r.id); menu.setOpen(open !== r.id || !menu.open); }}>⋮</button>
                    {open === r.id && menu.open && (
                      <RoleMenu
                        role={r}
                        right={r.id === 'client' || r.id === 'administrator'}
                        onReset={() => { roleActions.reset(r.id); menu.setOpen(false); setSaved(true); }}
                      />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {PERMISSION_GROUPS.map((g) => (
              <Fragment key={g.id}>
                <tr className={`group ${g.tone}`}><td colSpan={colspan}>{t(g.label)}</td></tr>
                {g.rows.map((row) => (
                  <tr key={row.id}>
                    <td>{t(row.label)}</td>
                    {ROLES.map((r) => <PermissionCell key={r.id} row={row} role={r} />)}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </section>
      {saved && (
        <Modal title="Role access saved" width={480} onClose={() => setSaved(false)}>
          <p className="bf-muted" style={{ margin: '10px 0 14px' }}>{t('Changes apply to users of these roles on their next page load.')}</p>
          <button type="button" className="bf-btn primary" onClick={() => setSaved(false)}>{t('Done')}</button>
        </Modal>
      )}
    </>
  );
}

function RoleMenu({ role, right, onReset }: { role: RoleColumn; right: boolean; onReset: () => void }) {
  const { t } = usePrefs();
  const style = right ? { right: 0, top: 28, textAlign: 'left' as const, fontWeight: 500 } : { left: -60, top: 28, textAlign: 'left' as const, fontWeight: 500 };
  if (role.fixed) {
    return (
      <div className="bf-menu" role="menu" style={style}>
        <a className="off" role="menuitem" aria-disabled="true">{t('Reset to default')}</a>
        <p className="note">{t('This role has fixed permissions.')}</p>
      </div>
    );
  }
  return (
    <div className="bf-menu" role="menu" style={style}>
      <button type="button" className="item" role="menuitem" onClick={onReset}>{t('Reset to default')}</button>
    </div>
  );
}

function PermissionCell({ row, role }: { row: PermissionRow; role: RoleColumn }) {
  const { t } = usePrefs();
  const cell = useRoleCell(row, role.id);
  if (cell === 'na') return <td>—</td>;
  if (cell === 'always') return <td>{t('Always')}</td>;
  const base = defaultCell(row, role.id) === 'on';
  return (
    <td>
      <input
        type="checkbox"
        className="bf-sw"
        checked={cell === 'on'}
        aria-label={`${t(row.label)}: ${t(role.name)}`}
        onChange={(e) => roleActions.set(role.id, row.id, e.target.checked, base)}
      />
    </td>
  );
}

// ---- Manage access (access-*.html) -------------------------------------------------------------------

export function AdminPersonAccessPage() {
  const { t } = usePrefs();
  const { userId = '', projectId = '' } = useParams();
  const list = useAdminUsers('', '', 'all');
  const users = list.data?.items ?? [];
  const user = users.find((u) => u.id === userId);

  if (!user) {
    return (
      <main className="bf-content">
        <Back to={paths.adminAccess} />
        <h2>{t(list.isPending ? 'Loading users' : 'User not found')}</h2>
      </main>
    );
  }

  const project = user.projects.find((p) => p.id === projectId);

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
        {user.projects.map((p) => (
          <Link key={p.id} className={project?.id === p.id ? 'on' : undefined} to={paths.adminAccessProject(user.id, p.id)}>{p.name}</Link>
        ))}
      </div>
      {project ? (
        <ProjectPermissions user={user} projectId={project.id} />
      ) : (
        <>
          <h3 style={{ fontSize: 18, margin: '37px 0 12px' }}>{t('Projects')}</h3>
          {!user.projects.length && <p className="bf-muted">{t('This person is not on any project yet.')}</p>}
          {user.projects.map((p) => (
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

function ProjectPermissions({ user, projectId }: { user: AdminUser; projectId: string }) {
  const { t } = usePrefs();
  const [step, setStep] = useState(0);
  const section = ACCESS_SECTIONS[step];
  return (
    <div className="bf-split">
      <nav className="bf-card bf-steps" aria-label={t('Permission sections')}>
        {ACCESS_SECTIONS.map((s, i) => (
          <button key={s.id} type="button" className={i === step ? 'on' : undefined} aria-current={i === step ? 'true' : undefined} onClick={() => setStep(i)}>
            {t(s.label)}
          </button>
        ))}
      </nav>
      <SectionPanel key={`${projectId}:${section.id}`} user={user} projectId={projectId} section={section} />
    </div>
  );
}

function SectionPanel({ user, projectId, section }: { user: AdminUser; projectId: string; section: AccessSection }) {
  const { t } = usePrefs();
  return (
    <section className="bf-card bf-panel">
      <header>
        <h3>{t(section.label)}</h3>
        <button type="button" onClick={() => accessActions.reset(user.id, projectId, section)}>{t('Reset to default')}</button>
      </header>
      {section.switches.map((s) => (
        <SwitchRow key={s.id} user={user} projectId={projectId} def={s} />
      ))}
    </section>
  );
}

function SwitchRow({ user, projectId, def }: { user: AdminUser; projectId: string; def: AccessSection['switches'][number] }) {
  const { t } = usePrefs();
  const on = useAccessSwitch(user.id, projectId, def, user.role);
  return (
    <label>
      {t(def.label)}
      <input type="checkbox" className="bf-sw" checked={on} onChange={(e) => accessActions.set(user.id, projectId, def, user.role, e.target.checked)} />
    </label>
  );
}
