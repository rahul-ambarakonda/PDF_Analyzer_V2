import { useQuery } from '@tanstack/react-query';

import { getJob } from '@/lib/api/comparison';
import type { JobResponse } from '@/types';

const POLL_INTERVAL_MS = 1500;

function isTerminal(status: JobResponse['status']): boolean {
  return status === 'completed' || status === 'failed';
}

/**
 * Polls a job until it reaches a terminal state, then stops refetching. Disabled while `jobId`
 * is null (before any comparison is started).
 */
export function useJob(jobId: string | null) {
  return useQuery<JobResponse>({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId as string),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && isTerminal(status) ? false : POLL_INTERVAL_MS;
    },
    // Job state is monotonic; don't serve stale terminal data across new runs.
    staleTime: 0,
    gcTime: 5 * 60 * 1000,
  });
}
