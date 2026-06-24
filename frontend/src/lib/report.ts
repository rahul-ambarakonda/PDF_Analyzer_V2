import type { JobResponse, ReportModel, ReportRow } from '../types';

export function buildReportModel(job: JobResponse): ReportModel {
  const rows: ReportRow[] = job.pairs.map((p) => ({
    name: p.name,
    status: p.status,
    defects: p.defect,
    review: p.review,
    qualityScore: p.quality_score ?? null,
    error: p.error ?? null,
    reportUrl: p.report_url ?? null,
  }));

  const totalIssues = job.pairs.reduce((sum, p) => sum + (p.defect || 0), 0);
  const totalReview = job.pairs.reduce((sum, p) => sum + (p.review || 0), 0);
  const cleanCount = job.pairs.filter((p) => p.status === 'clean').length;

  const scoredPairs = job.pairs.filter((p) => typeof p.quality_score === 'number');
  const overallScore = scoredPairs.length > 0
    ? Math.round(scoredPairs.reduce((sum, p) => sum + (p.quality_score as number), 0) / scoredPairs.length)
    : null;

  return {
    jobId: job.job_id,
    generatedAt: job.updated_at * 1000,
    fileCount: job.pairs.length,
    totalIssues,
    totalReview,
    cleanCount,
    overallScore,
    rows,
    unmatchedReference: job.unmatched_reference || [],
    unmatchedCandidate: job.unmatched_candidate || [],
  };
}
