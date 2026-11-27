import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { useAdminUsers } from './adminApi';
import {
  useActiveOrgMembers,
  useAddMemberTo,
  useCreateOrganisation,
  useOrganisation,
  useRemoveMemberFrom,
  useSetProjectContacts,
  useUpdateOrganisation,
  type CreatedMember,
  type OrgDetails,
} from './organisationsApi';
import { Back, EMAIL_RE, Field, Icon, ShareLinkModal, useAdminTitle } from './AdminUi';

interface Contact {
  key: number;
  /** Set for contacts that already exist: their name and email cannot be edited here. */
  id?: string;
  name: string;
  email: string;
}

const EMPTY_DETAILS: OrgDetails = { industry: '', website: '', primaryContactEmail: '', projectManagerId: '' };

const detailsOf = (org: { industry: string | null; website: string | null; primary_contact_email: string | null; project_manager: { id: string } | null } | undefined): OrgDetails =>
  org ? { industry: org.industry ?? '', website: org.website ?? '', primaryContactEmail: org.primary_contact_email ?? '', projectManagerId: org.project_manager?.id ?? '' } : EMPTY_DETAILS;

/** New client organisation (new-client-organisation.html) and Edit {organisation} (edit-org-*.html). */
export function AdminOrganisationFormPage() {
  const { orgId = '' } = useParams();
  const editing = !!orgId;
  const org = useOrganisation(orgId);
  if (editing && org.isPending) return <main className="bf-form-page"><p className="bf-muted">…</p></main>;
  if (editing && !org.data) return <NotFound />;
  return <OrganisationForm key={orgId} orgId={orgId} orgName={org.data?.name ?? ''} />;
}

function NotFound() {
  const { t } = usePrefs();
  useAdminTitle('Client organisations');
  return (
    <main className="bf-form-page">
      <Back to={paths.adminOrganisations} />
      <h1>{t('Organisation not found')}</h1>
      <p className="bf-sub">{t('It may have been removed. Go back to the organisation directory.')}</p>
    </main>
  );
}

function OrganisationForm({ orgId, orgName }: { orgId: string; orgName: string }) {
  const { t } = usePrefs();
  const toast = useToast();
  const navigate = useNavigate();
  const editing = !!orgId;
  const org = useOrganisation(orgId).data;
  const { members, isPending: membersPending } = useActiveOrgMembers(orgId);
  const create = useCreateOrganisation();
  const update = useUpdateOrganisation();
  const addMember = useAddMemberTo();
  const removeMember = useRemoveMemberFrom();
  const setProjectContacts = useSetProjectContacts();
  const managers = useAdminUsers('', 'account_manager', 'active').data?.items ?? [];
  const pms = useAdminUsers('', 'pm', 'active').data?.items ?? [];

  useAdminTitle(editing ? t('Edit {name}', { name: orgName }) : 'New client organisation');

  const nextKey = useRef(1);
  const blank = (): Contact => ({ key: nextKey.current++, name: '', email: '' });
  const [name, setName] = useState(orgName);
  const base = useMemo(() => detailsOf(org), [org]);
  const [extras, setExtras] = useState<OrgDetails>(base);
  // Project id -> chosen contact ids, for the projects the person changed.
  const [projectPicks, setProjectPicks] = useState<Record<string, string[]>>({});
  const [managerId, setManagerId] = useState(org?.account_managers[0]?.id ?? '');
  const [contacts, setContacts] = useState<Contact[]>(() => (editing ? [] : [blank()]));
  const [removed, setRemoved] = useState<string[]>([]);
  const [tried, setTried] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [links, setLinks] = useState<CreatedMember[]>([]);
  const [after, setAfter] = useState<string | null>(null);
  const loaded = useRef(false);

  // Existing contacts arrive after the first render.
  useEffect(() => {
    if (!editing || loaded.current || membersPending) return;
    loaded.current = true;
    // Until it is set, the primary contact is the first client contact.
    if (!base.primaryContactEmail && members[0]) setExtras((x) => ({ ...x, primaryContactEmail: x.primaryContactEmail || members[0].email }));
    setContacts(members.map((m) => ({ key: nextKey.current++, id: m.id, name: m.name, email: m.email })));
  }, [editing, members, membersPending, base.primaryContactEmail]);

  // Once every invitation link has been seen, leave.
  useEffect(() => {
    if (after && !links.length) navigate(after);
  }, [after, links.length, navigate]);

  const set = <K extends keyof OrgDetails>(k: K, v: OrgDetails[K]) => setExtras((e) => ({ ...e, [k]: v }));
  const setContact = (key: number, patch: Partial<Contact>) => setContacts((c) => c.map((x) => (x.key === key ? { ...x, ...patch } : x)));
  const visible = contacts.filter((c) => !(c.id && removed.includes(c.id)));
  const fresh = visible.filter((c) => !c.id);

  const errors = {
    name: name.trim() ? '' : 'Enter an organisation name.',
    primary: EMAIL_RE.test(extras.primaryContactEmail.trim()) ? '' : 'Enter a valid email address.',
  };
  const contactError = (c: Contact) => {
    if (c.id || (!c.name.trim() && !c.email.trim())) return '';
    if (!c.name.trim()) return 'Enter a name.';
    if (!EMAIL_RE.test(c.email.trim())) return 'Enter a valid email address.';
    return '';
  };

  const dirty =
    !editing ||
    name.trim() !== orgName ||
    managerId !== (org?.account_managers[0]?.id ?? '') ||
    (Object.keys(extras) as (keyof OrgDetails)[]).some((k) => extras[k] !== base[k]) ||
    Object.keys(projectPicks).length > 0 ||
    removed.length > 0 ||
    fresh.some((c) => c.name.trim() || c.email.trim());

  const save = async () => {
    setTried(true);
    setError('');
    if (errors.name || errors.primary || visible.some((c) => contactError(c)) || Object.values(projectPicks).some((ids) => !ids.length)) return;
    setBusy(true);
    let id = orgId;
    try {
      if (editing && org) {
        await update.mutateAsync({ org, name: name.trim(), managerId, details: extras });
      } else {
        id = (await create.mutateAsync({ name: name.trim(), managerId, details: extras })).id;
      }
      // Before anyone is removed, so a project never loses its last named contact on the way.
      for (const [projectId, userIds] of Object.entries(projectPicks)) await setProjectContacts.mutateAsync({ orgId: id, projectId, userIds });
      for (const userId of removed) await removeMember.mutateAsync({ orgId: id, userId });
      const created: CreatedMember[] = [];
      for (const c of fresh.filter((x) => x.name.trim() && x.email.trim())) {
        created.push(await addMember.mutateAsync({ orgId: id, name: c.name.trim(), email: c.email.trim() }));
      }
      toast.success(editing ? 'Organisation updated.' : 'Organisation added.');
      setLinks(created);
      setAfter(editing ? paths.adminOrganisations : paths.adminOrganisation(id));
    } catch (e) {
      const message = describeApiError(e, t('That didn’t work. Try again.'));
      if (!editing && id) {
        // The organisation exists now: carry on from its edit page rather than creating it twice.
        toast.error(message);
        navigate(paths.adminOrganisation(id), { replace: true });
        return;
      }
      setError(message);
      setBusy(false);
    }
  };

  const heading = editing ? t('Edit {name}', { name: orgName }) : t('New client organisation');

  return (
    <main className="bf-form-page">
      <Back to={paths.adminOrganisations} />
      <h1>{heading}</h1>
      <p className="bf-sub">{t(editing ? 'Update organisation details, team assignments and client contacts.' : 'Register the company, assign its team and add client contacts.')}</p>
      <form className="bf-card bf-form-card" noValidate onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <div className="bf-sec">
          <div className="bf-aside">
            <span className="bf-ico"><Icon><path d="M4 21V8l8-5 8 5v13zM9 10h.01M15 10h.01M9 14h.01M15 14h.01M10 21v-3h4v3" /></Icon></span>
            <h3>{t('Organisation details')}</h3>
            <p>{t('Enter the company’s basic information.')}</p>
          </div>
          <div className="bf-grid">
            <Field label="Organisation name *" error={tried ? errors.name : ''}>
              <input className="bf-input" type="text" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="off" />
            </Field>
            <Field label="Industry">
              <input className="bf-input" type="text" value={extras.industry} onChange={(e) => set('industry', e.target.value)} maxLength={100} autoComplete="off" />
            </Field>
            <Field label="Website">
              <input className="bf-input" type="text" value={extras.website} onChange={(e) => set('website', e.target.value)} maxLength={200} autoComplete="off" />
            </Field>
            <Field label="Primary contact email *" error={tried ? errors.primary : ''}>
              <input className="bf-input" type="email" value={extras.primaryContactEmail} onChange={(e) => set('primaryContactEmail', e.target.value)} maxLength={320} autoComplete="off" />
            </Field>
          </div>
        </div>

        <div className="bf-sec">
          <div className="bf-aside">
            <span className="bf-ico"><Icon><circle cx="9" cy="8" r="4" /><path d="M2 21c0-8 14-8 14 0M16 4a4 4 0 0 1 0 8M18 15c3 1 4 3 4 6" /></Icon></span>
            <h3>{t('Assign team')}</h3>
            <p>{t(editing ? 'Review the account and project managers assigned to this organisation.' : 'Choose who manages the account and leads its first project.')}</p>
          </div>
          <div className="bf-grid">
            <Field label="Account Manager">
              <select value={managerId} onChange={(e) => setManagerId(e.target.value)}>
                <option value="">{t('Select Account Manager')}</option>
                {managers.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </Field>
            <Field label="Project Manager (optional)">
              <select value={extras.projectManagerId} onChange={(e) => set('projectManagerId', e.target.value)}>
                <option value="">{t('Select Project Manager')}</option>
                {pms.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </Field>
          </div>
        </div>

        <div className="bf-sec">
          <div className="bf-aside">
            <span className="bf-ico"><Icon><rect x="3" y="4" width="18" height="16" rx="1" /><circle cx="9" cy="10" r="2" /><path d="M6 16c0-4 6-4 6 0M15 9h3M15 13h3" /></Icon></span>
            <h3>{t('Client accounts')}</h3>
            <p>{t(editing ? 'Manage the client contacts for this organisation.' : 'Project access is assigned after the organisation is created.')}</p>
          </div>
          <div style={{ flex: 1 }}>
            {visible.map((c) => {
              const bad = tried ? contactError(c) : '';
              return (
                <div className="bf-contact" key={c.key}>
                  <Field label="Full name" error={bad === 'Enter a name.' ? bad : ''}>
                    <input className="bf-input" type="text" value={c.name} readOnly={!!c.id} onChange={(e) => setContact(c.key, { name: e.target.value })} maxLength={200} autoComplete="off" />
                  </Field>
                  <Field label="Work email" error={bad && bad !== 'Enter a name.' ? bad : ''}>
                    <input className="bf-input" type="email" value={c.email} readOnly={!!c.id} onChange={(e) => setContact(c.key, { email: e.target.value })} maxLength={320} autoComplete="off" />
                  </Field>
                  <div className="end">
                    {editing ? t('Action') : t('Role')}
                    <div>
                      {editing ? (
                        <button
                          type="button"
                          className="bf-link"
                          aria-label={`${t('Remove')} ${c.name}`}
                          onClick={() => (c.id ? setRemoved((r) => [...r, c.id as string]) : setContacts((all) => all.filter((x) => x.key !== c.key)))}
                        >
                          {t('Remove')}
                        </button>
                      ) : (
                        t('Client')
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            <button type="button" className="bf-btn green" style={{ marginTop: 4, height: 33 }} onClick={() => setContacts((c) => [...c, blank()])}>＋ {t('Add another contact')}</button>
          </div>
        </div>

        {editing && !!org?.projects.length && (
          <div className="bf-sec">
            <div className="bf-aside">
              <span className="bf-ico"><Icon><path d="M3 7h18M3 12h18M3 17h12" /></Icon></span>
              <h3>{t('Project contacts')}</h3>
              <p>{t('Choose the named client contacts of each project. Each project needs at least one.')}</p>
            </div>
            <div style={{ flex: 1 }}>
              {org.projects.map((p) => {
                const chosen = (projectPicks[p.id] ?? p.contacts.map((c) => c.id)).filter((x) => !removed.includes(x));
                const options = members.filter((m) => !removed.includes(m.id));
                return (
                  <fieldset key={p.id} style={{ border: 0, padding: 0, margin: '0 0 14px' }}>
                    <legend><b>{p.name}</b></legend>
                    {!options.length && <p className="bf-muted">{t('Add a client contact first.')}</p>}
                    {options.map((m) => (
                      <label key={m.id} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '4px 0' }}>
                        <input
                          type="checkbox"
                          checked={chosen.includes(m.id)}
                          onChange={(e) => {
                            const next = e.target.checked ? [...chosen, m.id] : chosen.filter((x) => x !== m.id);
                            setProjectPicks((all) => ({ ...all, [p.id]: next }));
                          }}
                        />
                        {m.name} <span className="bf-muted">{m.email}</span>
                      </label>
                    ))}
                    {projectPicks[p.id] && !projectPicks[p.id].length && <p className="bf-error" role="alert">{t('Choose at least one contact.')}</p>}
                  </fieldset>
                );
              })}
            </div>
          </div>
        )}

        {error && <p className="bf-error" role="alert" style={{ padding: '12px 24px 0' }}>{error}</p>}
        <div className="bf-actions">
          <Link className="bf-btn lg" to={paths.adminOrganisations}>{t('Cancel')}</Link>
          <button type="submit" className={editing ? 'bf-btn lg' : 'bf-btn primary lg'} disabled={busy || !dirty}>{t(editing ? 'Save changes' : 'Create organisation')}</button>
        </div>
      </form>
      {links[0] && (
        <ShareLinkModal
          key={links[0].member.id}
          name={links[0].member.name}
          email={links[0].member.email}
          url={links[0].invite.url}
          expiresAt={links[0].invite.expires_at}
          onClose={() => setLinks((l) => l.slice(1))}
        />
      )}
    </main>
  );
}
