import type { ReportRow } from '@/types';

const STATUS_LABEL: Record<ReportRow['status'], string> = {
  clean: 'Clean',
  defect: 'Defect',
  error: 'Error',
  pending: 'Pending',
};

function statusColor(status: ReportRow['status']): string {
  if (status === 'defect') return '#dc2626';
  if (status === 'error') return '#f59e0b';
  if (status === 'clean') return '#16a34a';
  return '#64748b';
}

/** Per-file results: status, defect/review counts, score, and a link to the HTML report. */
export function FileResultsTable({ rows }: { rows: ReportRow[] }) {
  if (!rows.length) return null;
  return (
    <div className="rc-file-table">
      <div className="rc-file-header file-results-header">
        <span>File</span>
        <span style={{ textAlign: 'center' }}>Status</span>
        <span style={{ textAlign: 'right' }}>Defects</span>
        <span style={{ textAlign: 'right' }}>Score</span>
        <span style={{ textAlign: 'right' }}>Report</span>
      </div>
      {rows.map((row) => (
        <div key={row.name} className="rc-file-row file-results-row">
          <span title={row.error ?? undefined}>{row.name}</span>
          <strong style={{ textAlign: 'center', color: statusColor(row.status) }}>
            {STATUS_LABEL[row.status]}
          </strong>
          <strong style={{ textAlign: 'right', color: row.defects ? '#dc2626' : '#16a34a' }}>
            {row.status === 'error' ? '—' : row.defects}
          </strong>
          <span style={{ textAlign: 'right' }}>
            {row.qualityScore === null ? '—' : `${row.qualityScore}/100`}
          </span>
          <span style={{ textAlign: 'right' }}>
            {row.reportUrl ? (
              <a className="report-link" href={row.reportUrl} target="_blank" rel="noreferrer">
                View →
              </a>
            ) : (
              '—'
            )}
          </span>
        </div>
      ))}
    </div>
  );
}
