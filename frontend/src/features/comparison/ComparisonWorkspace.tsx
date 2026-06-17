import { useMemo, useReducer } from 'react';

import { Modal } from '@/components/ui/Modal';
import { ReportPanel } from '@/features/comparison/ReportPanel';
import { SourcePanel } from '@/features/comparison/SourcePanel';
import {
  initialWorkspaceState,
  workspaceReducer,
} from '@/features/comparison/workspaceReducer';
import { useJob } from '@/hooks/useJob';
import { useStartComparison } from '@/hooks/useStartComparison';
import { buildReportModel } from '@/lib/report';
import type { FolderFile } from '@/types';

export function ComparisonWorkspace() {
  const [state, dispatch] = useReducer(workspaceReducer, initialWorkspaceState);
  const startMutation = useStartComparison();
  const jobQuery = useJob(state.jobId);

  const job = jobQuery.data;
  const report = useMemo(
    () => (job && job.status === 'completed' ? buildReportModel(job) : null),
    [job],
  );

  const isProcessing =
    startMutation.isPending ||
    (state.jobId !== null && (!job || (job.status !== 'completed' && job.status !== 'failed')));

  const errorMessage = (() => {
    if (startMutation.isError) return startMutation.error.message;
    if (job?.status === 'failed') return job.error ?? 'Comparison failed.';
    if (jobQuery.isError) return (jobQuery.error as Error).message;
    return null;
  })();

  const statusText = (() => {
    if (startMutation.isPending) return 'Uploading…';
    if (state.jobId !== null) {
      if (!job) return 'Starting…';
      if (job.status === 'queued') return 'Queued…';
      if (job.status === 'running') return 'Comparing…';
      if (job.status === 'completed') return 'Report ready';
      if (job.status === 'failed') return 'Comparison failed';
    }
    if (state.reference.length && state.candidate.length) return 'Ready to compare';
    if (state.reference.length || state.candidate.length) return 'Select both folders';
    return 'Waiting for folder selections';
  })();

  const openAlert = (title: string, message: string) =>
    dispatch({ type: 'openAlert', title, message });

  const handleSelectReference = (files: FolderFile[], label: string) =>
    dispatch({ type: 'setReference', files, label });
  const handleSelectCandidate = (files: FolderFile[], label: string) =>
    dispatch({ type: 'setCandidate', files, label });

  const handleGenerate = () => {
    if (!state.reference.length || !state.candidate.length) {
      openAlert('Folder selection', 'Please select both a reference folder and a Creo folder.');
      return;
    }
    startMutation.mutate(
      { reference: state.reference, candidate: state.candidate },
      {
        onSuccess: (data) => dispatch({ type: 'setJob', jobId: data.job_id }),
        onError: (err) => openAlert('Comparison error', err.message),
      },
    );
  };

  return (
    <main className="app-shell">
      <header className="hero">
        <div className="hero-copyblock">
          <p className="eyebrow">CREO FILE WORKSPACE</p>
          <h1>Compare reference and Creo drawing PDFs and review text-fidelity defects.</h1>
        </div>
        <div className="hero-badge">
          <span className="badge-label">Files compared</span>
          <strong>{report?.fileCount ?? 0}</strong>
        </div>
      </header>

      <SourcePanel
        format={state.format}
        onFormatChange={(format) => dispatch({ type: 'setFormat', format })}
        referenceCount={state.reference.length}
        candidateCount={state.candidate.length}
        hasReport={report !== null}
        isProcessing={isProcessing}
        canGenerate={state.reference.length > 0 && state.candidate.length > 0 && !isProcessing}
        statusText={errorMessage ?? statusText}
        statusOk={report !== null && !errorMessage}
        onSelectReference={handleSelectReference}
        onSelectCandidate={handleSelectCandidate}
        onInvalid={(message) => openAlert('Folder selection', message)}
        onGenerate={handleGenerate}
      />

      <ReportPanel
        report={report}
        isProcessing={isProcessing}
        errorMessage={errorMessage}
        referenceCount={state.reference.length}
        candidateCount={state.candidate.length}
      />

      <Modal
        open={state.alert.open}
        title={state.alert.title}
        message={state.alert.message}
        onClose={() => dispatch({ type: 'closeAlert' })}
      />
    </main>
  );
}
