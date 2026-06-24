import { z } from 'zod';

export const pairStatusSchema = z.enum(['pending', 'clean', 'defect', 'error']);

export const pairSummarySchema = z.object({
  name: z.string(),
  status: pairStatusSchema,
  total_defects: z.number().default(0),
  defect: z.number().default(0),
  review: z.number().default(0),
  quality_score: z.number().nullable().optional().default(null),
  error: z.string().nullable().optional().default(null),
  report_url: z.string().nullable().optional().default(null),
});

export const compareAcceptedSchema = z.object({
  job_id: z.string(),
  status: z.string(),
  pair_count: z.number(),
  unmatched_reference: z.array(z.string()).default([]),
  unmatched_candidate: z.array(z.string()).default([]),
});

export const jobStatusSchema = z.enum(['queued', 'running', 'completed', 'failed']);

export const jobResponseSchema = z.object({
  job_id: z.string(),
  status: jobStatusSchema,
  created_at: z.number(),
  updated_at: z.number(),
  pairs: z.array(pairSummarySchema).default([]),
  unmatched_reference: z.array(z.string()).default([]),
  unmatched_candidate: z.array(z.string()).default([]),
  error: z.string().nullable().optional().default(null),
});

export const errorResponseSchema = z.object({
  error: z.string(),
  detail: z.string().nullable().optional().default(null),
  request_id: z.string().nullable().optional().default(null),
});
