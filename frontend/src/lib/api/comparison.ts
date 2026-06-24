import { request } from './client';
import { compareAcceptedSchema, jobResponseSchema } from '../schemas';
import type { CompareAccepted, JobResponse, FolderFile } from '@/types';

export async function startComparison(
  reference: FolderFile[],
  candidate: FolderFile[]
): Promise<CompareAccepted> {
  const formData = new FormData();
  
  reference.forEach((item) => {
    formData.append('reference', item.file, item.name);
  });
  
  candidate.forEach((item) => {
    formData.append('candidate', item.file, item.name);
  });

  return request<CompareAccepted>('/api/v1/compare', {
    method: 'POST',
    body: formData,
  }, compareAcceptedSchema);
}

export async function getJob(jobId: string): Promise<JobResponse> {
  return request<JobResponse>(`/api/v1/jobs/${jobId}`, {
    method: 'GET',
  }, jobResponseSchema);
}
