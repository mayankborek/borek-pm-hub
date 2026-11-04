import { useEffect, useState } from 'react';
import { describeApiError } from '@/shared/api/client';
import { usePrefs } from '@/shared/prefs/PrefsContext';
import type { Project } from '@/features/projects/types';
import { useCommitImport, useImportJob, usePreviewImport, type DuplicatePolicy, type ImportPreview } from './jiraApi';
import './taskDetail.css'; // drawer styles (rd-*) shared with RelatedTaskDrawer

interface Props {
  projects: Project[];
  defaultProjectId: string;
  onClose: () => void;
}

/** Jira import in three steps: choose project + file, review the dry-run preview, then watch the import job. */
export function JiraImportDialog({ projects, defaultProjectId, onClose }: Props) {
  const { t: tr } = usePrefs();
  const [projectId, setProjectId] = useState(defaultProjectId);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [onDuplicate, setOnDuplicate] = useState<DuplicatePolicy>('skip');
  const [createStatuses, setCreateStatuses] = useState(false);
  const [jobId, setJobId] = useState<string>();
  const previewImport = usePreviewImport();
  const commit = useCommitImport();
  const job = useImportJob(jobId).data;
  const running = !!jobId && job?.status !== 'completed' && job?.status !== 'failed';

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !running && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, running]);

  const error = previewImport.error ?? commit.error;
  const importable = preview ? preview.new_count + (onDuplicate === 'update' ? preview.duplicate_count : 0) : 0;

  return (
    <div className="rd-overlay">
      <button type="button" className="rd-dismiss" aria-label={tr('Dismiss drawer')} onClick={() => !running && onClose()} />
      <aside className="rd-drawer" role="dialog" aria-modal="true" aria-labelledby="ji-title">
        <div className="rd-content">
          <div className="rd-head">
            <h2 id="ji-title">{tr('Import')}</h2>
            <button type="button" className="btn secondary rd-close" disabled={running} onClick={onClose}>
              {tr('Close')}
            </button>
          </div>
          <hr className="rd-rule" />

          {!preview && (
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
                <label htmlFor="ji-file">{tr('Jira export file')}</label>
                <input id="ji-file" type="file" accept=".csv,.json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                <p className="muted small">{tr('In Jira: Filters → View all issues → Export → CSV (all fields), or a Jira JSON export.')}</p>
              </div>
            </>
          )}

          {preview && !jobId && (
            <>
              <p>
                <strong>{preview.file_name}</strong> · {tr('{n} rows', { n: preview.total_rows })}
              </p>
              <ul className="ji-stats">
                <li>{tr('{n} new', { n: preview.new_count })}</li>
                <li>{tr('{n} already imported', { n: preview.duplicate_count })}</li>
                <li className={preview.invalid_count ? 'err' : ''}>{tr('{n} invalid', { n: preview.invalid_count })}</li>
              </ul>
              {preview.unmapped_statuses.length > 0 && (
                <>
                  <p className="warn">{tr('Statuses not in this project: {list}', { list: preview.unmapped_statuses.join(', ') })}</p>
                  <label className="ji-check">
                    <input type="checkbox" checked={createStatuses} onChange={(e) => setCreateStatuses(e.target.checked)} />
                    {tr('Create the missing statuses (otherwise they land in the first backlog status)')}
                  </label>
                </>
              )}
              {preview.unmapped_assignees.length > 0 && (
                <p className="muted small">{tr('No matching user, will be unassigned: {list}', { list: preview.unmapped_assignees.join(', ') })}</p>
              )}
              {preview.duplicate_count > 0 && (
                <div className="rd-field">
                  <label htmlFor="ji-dup">{tr('Tasks already imported')}</label>
                  <select id="ji-dup" value={onDuplicate} onChange={(e) => setOnDuplicate(e.target.value as DuplicatePolicy)}>
                    <option value="skip">{tr('Skip them')}</option>
                    <option value="update">{tr('Update them from the file')}</option>
                  </select>
                </div>
              )}
              {preview.errors.length > 0 && (
                <ul className="ji-errors">
                  {preview.errors.slice(0, 20).map((e, i) => (
                    <li key={i}>
                      {tr('Row {row}', { row: e.row })}
                      {e.jira_key ? ` (${e.jira_key})` : ''}: {e.message}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}

          {jobId && (
            <div role="status">
              {job?.status === 'completed' || job?.status === 'failed' ? (
                <>
                  <p className={job.status === 'failed' ? 'err' : 'warn'}>
                    {tr(job.status === 'failed' ? 'Import failed.' : 'Import finished.')}
                  </p>
                  <ul className="ji-stats">
                    <li>{tr('{n} created', { n: job.created })}</li>
                    <li>{tr('{n} updated', { n: job.updated })}</li>
                    <li>{tr('{n} skipped', { n: job.skipped })}</li>
                    <li className={job.failed ? 'err' : ''}>{tr('{n} failed', { n: job.failed })}</li>
                  </ul>
                  {job.errors.length > 0 && (
                    <ul className="ji-errors">
                      {job.errors.slice(0, 20).map((e, i) => (
                        <li key={i}>
                          {tr('Row {row}', { row: e.row })}: {e.message}
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              ) : (
                <p>{tr('Importing… {done} of {total}', { done: job?.processed ?? 0, total: job?.total ?? preview?.total_rows ?? 0 })}</p>
              )}
            </div>
          )}

          {error && (
            <p className="err" role="alert">
              {describeApiError(error, tr('Jira import failed.'))}
            </p>
          )}
        </div>

        <div className="rd-footer">
          {job?.status === 'completed' || job?.status === 'failed' ? (
            <button type="button" className="btn rd-btn" onClick={onClose}>
              {tr('Done')}
            </button>
          ) : !preview ? (
            <button
              type="button"
              className="btn rd-btn"
              disabled={!projectId || !file || previewImport.isPending}
              onClick={() => file && previewImport.mutate({ projectId, file }, { onSuccess: setPreview })}
            >
              {tr(previewImport.isPending ? 'Checking…' : 'Preview import')}
            </button>
          ) : (
            <>
              <button type="button" className="btn secondary rd-btn" disabled={running} onClick={() => setPreview(null)}>
                {tr('Back')}
              </button>
              <button
                type="button"
                className="btn rd-btn"
                disabled={running || commit.isPending || importable === 0}
                onClick={() =>
                  commit.mutate(
                    { batchId: preview.batch_id, on_duplicate: onDuplicate, create_missing_statuses: createStatuses },
                    { onSuccess: (j) => setJobId(j.id) },
                  )
                }
              >
                {tr('Import {n} tasks', { n: importable })}
              </button>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}
