import type { z } from 'zod';
import type {
  compareAcceptedSchema,
  jobResponseSchema,
  jobStatusSchema,
  pairStatusSchema,
  pairSummarySchema,
} from '@/lib/schemas';

export type JobStatus = z.infer<typeof jobStatusSchema>;
export type PairStatus = z.infer<typeof pairStatusSchema>;
export type PairSummary = z.infer<typeof pairSummarySchema>;
export type CompareAccepted = z.infer<typeof compareAcceptedSchema>;
export type JobResponse = z.infer<typeof jobResponseSchema>;

/** A user-selected PDF plus the folder-relative path used for pairing. */
export interface FolderFile {
  file: File;
  name: string;
  path: string;
  size: number;
}

/** Aggregated, view-ready model derived from a completed job. */
export interface ReportModel {
  jobId: string;
  generatedAt: number;
  fileCount: number;
  totalIssues: number;
  totalReview: number;
  cleanCount: number;
  overallScore: number | null;
  rows: ReportRow[];
  unmatchedReference: string[];
  unmatchedCandidate: string[];
}

export interface ReportRow {
  name: string;
  status: PairStatus;
  defects: number;
  review: number;
  qualityScore: number | null;
  error?: string | null;
  reportUrl?: string | null;
}
