import { Spinner } from '@/components/ui/Spinner';
import { StatusPill } from '@/components/ui/StatusPill';
import { FileResultsTable } from '@/features/comparison/FileResultsTable';
import { formatTimestamp } from '@/lib/format';
import type { ReportModel } from '@/types';

interface ReportPanelProps {
  report: ReportModel | null;
  isProcessing: boolean;
  errorMessage: string | null;
  referenceCount: number;
  candidateCount: number;
}

export function ReportPanel({
  report,
  isProcessing,
  errorMessage,
  referenceCount,
  candidateCount,
}: ReportPanelProps) {
  const unmatched = report
    ? [
        ...report.unmatchedReference.map((n) => `Reference “${n}” had no Creo match`),
        ...report.unmatchedCandidate.map((n) => `Creo “${n}” had no reference match`),
      ]
    : [];

  return (
    <div className="panel output-panel">
      <div className="output-header">
        <div>
          <p className="panel-kicker">Output</p>
          <h2>Report</h2>
        </div>
        <div className="output-metrics">
          <div className="metric-chip">
            <span>Reference PDFs</span>
            <strong>{referenceCount}</strong>
          </div>
          <div className="metric-chip">
            <span>Creo PDFs</span>
            <strong>{candidateCount}</strong>
          </div>
          <div className="metric-chip">
            <span>Files compared</span>
            <strong>{report?.fileCount ?? 0}</strong>
          </div>
        </div>
      </div>

      <div className="report-cards-grid report-cards-single">
        <div className="report-card">
          <div className="rc-header">
            <div className="rc-title">
              <span className="rc-badge">🔍</span>
              <div>
                <h3>Compliance Report</h3>
                <span className="rc-subtitle">TEXT-FIDELITY AUDIT</span>
              </div>
            </div>
            <StatusPill tone={report ? 'done' : 'wait'}>
              {report ? 'Completed' : 'Awaiting run'}
            </StatusPill>
          </div>
          <p className="rc-desc">
            Text/annotation fidelity audit between source drawings and Creo review drawings.
          </p>

          {isProcessing ? (
            <div style={{ padding: '8px 0' }}>
              <Spinner label="Generating report" />
            </div>
          ) : errorMessage ? (
            <div className="rc-error">{errorMessage}</div>
          ) : report ? (
            <>
              <div className="rc-meta">
                <div className="rc-meta-row">
                  📄 Generated: <strong>{formatTimestamp(new Date(report.generatedAt))}</strong>
                </div>
                <div className="rc-meta-row">
                  📋 Files Compared: <strong>{report.fileCount}</strong>
                </div>
                <div className="rc-meta-row">
                  ⚠ Defects Flagged:{' '}
                  <strong style={{ color: report.totalIssues ? '#dc2626' : '#16a34a' }}>
                    {report.totalIssues}
                  </strong>
                </div>
                {report.totalReview > 0 && (
                  <div className="rc-meta-row">
                    🔎 To Review: <strong style={{ color: '#d97706' }}>{report.totalReview}</strong>
                  </div>
                )}
              </div>

              <div className="rc-summary">
                <div className="rc-sum-item">
                  <span>Clean</span>
                  <strong style={{ color: '#16a34a' }}>
                    {report.cleanCount}/{report.fileCount}
                  </strong>
                </div>
                <div className="rc-sum-item">
                  <span>Defects</span>
                  <strong style={{ color: '#dc2626' }}>{report.totalIssues}</strong>
                </div>
                <div className="rc-sum-item">
                  <span>Score</span>
                  <strong>{report.overallScore === null ? '—' : `${report.overallScore}/100`}</strong>
                </div>
              </div>

              <FileResultsTable rows={report.rows} />

              {unmatched.length > 0 && (
                <div className="rc-warning">
                  {unmatched.map((line) => (
                    <div key={line}>⚠ {line}</div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="rc-placeholder">
              Select a reference folder and a Creo folder, then run the comparison.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
