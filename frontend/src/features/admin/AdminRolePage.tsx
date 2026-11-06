import { useParams } from 'react-router-dom';
import { paths } from '@/app/routes';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import { useToast } from '@/shared/ui/Toast';
import { Back } from './Back';
import { AREAS, ROLES, isCustomised, permissionActions, usePermissions, type Access } from './adminStore';

const LEVELS: Access[] = ['view', 'edit', 'denied'];
const LEVEL_LABEL: Record<Access, string> = { view: 'View', edit: 'Edit', denied: 'Denied' };

export function AdminRolePage() {
  const { t } = usePrefs();
  const toast = useToast();
  const { roleId = '' } = useParams();
  const role = ROLES.find((r) => r.id === roleId);
  const perms = usePermissions(roleId);

  if (!role) {
    return (
      <>
        <Back to={paths.adminRoles} label="All roles" />
        <h2 className="ad-title ad-gap">{t('Role not found')}</h2>
      </>
    );
  }

  const roleName = t(role.name);
  const customised = isCustomised(role.id, perms);

  return (
    <>
      <Back to={paths.adminRoles} label="All roles" />
      <div className="ad-head ad-gap">
        <h2 className="ad-title ad-title--lg">{t('{role} permissions', { role: roleName })}</h2>
        <button
          type="button"
          className="ad-link"
          disabled={!customised}
          onClick={() => {
            permissionActions.reset(role.id);
            toast.success('Permissions reset to default.');
          }}
        >
          {t('Reset to default')}
        </button>
      </div>
      <p className="ad-lead">{t('Choose one access level for each area.')}</p>

      <div className="ad-matrix" role="table" aria-label={t('{role} permissions', { role: roleName })}>
        <div className="ad-matrix-head" role="row">
          <span role="columnheader">{t('Area')}</span>
          <span role="columnheader">{t('Includes')}</span>
          {LEVELS.map((l) => <span key={l} role="columnheader" className="c">{t(LEVEL_LABEL[l])}</span>)}
        </div>
        {AREAS.map((a) => (
          <div className="ad-matrix-row" role="row" key={a.id}>
            <span role="cell" className="area">{t(a.label)}</span>
            <span role="cell" className="incl">{t(a.includes)}</span>
            {LEVELS.map((l) => (
              <span role="cell" className="c" key={l}>
                <input
                  className="ad-radio"
                  type="radio"
                  name={`${role.id}-${a.id}`}
                  value={l}
                  checked={perms[a.id] === l}
                  aria-label={`${t(a.label)}: ${t(LEVEL_LABEL[l]).toLowerCase()}`}
                  onChange={() => permissionActions.set(role.id, a.id, l)}
                />
              </span>
            ))}
          </div>
        ))}
      </div>
      <p className="ad-hint ad-note">{t('Changes are saved automatically in this browser.')}</p>
    </>
  );
}
