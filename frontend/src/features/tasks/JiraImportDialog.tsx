import { useEffect, useState } from 'react';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import type { Project } from '@/features/projects/types';
import { useImportTasks, type ImportResult } from './jiraApi';
import './taskDetail.css'; // drawer styles (rd-*) shared with RelatedTaskDrawer

interface Props {
  projects: Project[];
  defaultProjectId: string;
  onClose: () => void;
}

/** CSV import in two steps: choose project + file and review the dry-run check, then save it. */
export function JiraImportDialog({ projects, defaultProjectId, onClose }: Props) {
  const { t: tr } = usePrefs();
  const [projectId, setProjectId] = useState(defaultProjectId);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const importTasks = useImportTasks();
  const saved = !!result && !result.dry_run;
  const busy = importTasks.isPending;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !busy && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);

  const run = (dryRun: boolean) => file && importTasks.mutate({ projectId, file, dryRun }, { onSuccess: setResult });
  const unknownStatuses = Object.entries(result?.unknown_statuses ?? {});

  return (
    <div className="rd-overlay">
      <button type="button" className="rd-dismiss" aria-label={tr('Dismiss drawer')} onClick={() => !busy && onClose()} />
      <aside className="rd-drawer" role="dialog" aria-modal="true" aria-labelledby="ji-title">
        <div className="rd-content">
          <div className="rd-head">
            <h2 id="ji-title">{tr('Import')}</h2>
            <button type="button" className="btn secondary rd-close" disabled={busy} onClick={onClose}>
              {tr('Close')}
            </button>
          </div>
          <hr className="rd-rule" />

          {!result && (
            <>
              <div className="rd-field">
                <label htmlFor="ji-project">{tr('Project')}</label>
                <select id="ji-project" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                  <option value="">{tr('Select a project')}</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="rd-field">
                <label htmlFor="ji-file">{tr('CSV file')}</label>
                <input id="ji-file" type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                <p className="muted small">{tr('A Jira CSV export (Filters → View all issues → Export → CSV) or a file exported from here.')}</p>
              </div>
            </>
          )}

          {result && (
            <>
              <p>
                <strong>{file?.name}</strong> · {tr('{n} rows', { n: result.total_rows })}
              </p>
              {saved && <p className="warn">{tr('Import finished.')}</p>}
              <ul className="ji-stats">
                <li>{tr(saved ? '{n} created' : '{n} new', { n: result.created })}</li>
                <li>{tr('{n} already imported', { n: result.skipped_existing })}</li>
                <li className={result.failed ? 'err' : ''}>{tr('{n} invalid', { n: result.failed })}</li>
              </ul>
              {unknownStatuses.length > 0 && (
                <p className="warn">
                  {tr('Statuses not in this project: {list}', { list: unknownStatuses.map(([from, to]) => `${from} → ${to}`).join(', ') })}
                </p>
              )}
              {result.unknown_assignees.length > 0 && (
                <p className="muted small">{tr('No matching user, will be unassigned: {list}', { list: result.unknown_assignees.join(', ') })}</p>
              )}
              {result.other_projects_in_file.length > 0 && (
                <p className="muted small">{tr('More than one project in the file: {list}', { list: result.other_projects_in_file.join(', ') })}</p>
              )}
              {result.failures.length > 0 && (
                <ul className="ji-errors">
                  {result.failures.slice(0, 20).map((e, i) => (
                    <li key={i}>
                      {tr('Row {row}', { row: e.row })}
                      {e.external_key ? ` (${e.external_key})` : ''}: {e.message}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}

          {importTasks.error && (
            <p className="err" role="alert">
              {describeApiError(importTasks.error, tr('Import failed.'))}
            </p>
          )}
        </div>

        <div className="rd-footer">
          {saved ? (
            <button type="button" className="btn rd-btn" onClick={onClose}>
              {tr('Done')}
            </button>
          ) : !result ? (
            <button type="button" className="btn rd-btn" disabled={!projectId || !file || busy} onClick={() => run(true)}>
              {tr(busy ? 'Checking…' : 'Preview import')}
            </button>
          ) : (
            <>
              <button type="button" className="btn secondary rd-btn" disabled={busy} onClick={() => setResult(null)}>
                {tr('Back')}
              </button>
              <button type="button" className="btn rd-btn" disabled={busy || result.created === 0} onClick={() => run(false)}>
                {tr(busy ? 'Importing…' : 'Import {n} tasks', { n: result.created })}
              </button>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
