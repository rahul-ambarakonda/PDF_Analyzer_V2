import { useMutation } from '@tanstack/react-query';

import { startComparison } from '@/lib/api/comparison';
import type { CompareAccepted, FolderFile } from '@/types';

export interface StartComparisonVars {
  reference: FolderFile[];
  candidate: FolderFile[];
}

/** Mutation that uploads the two folders and enqueues a comparison job. */
export function useStartComparison() {
  return useMutation<CompareAccepted, Error, StartComparisonVars>({
    mutationFn: ({ reference, candidate }) => startComparison(reference, candidate),
  });
}
