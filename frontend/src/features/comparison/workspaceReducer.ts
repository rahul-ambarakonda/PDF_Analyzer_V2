/** Local client state for the comparison workspace (folder selections, format, alert, job id). */
import type { FolderFile } from '@/types';

export interface AlertState {
  open: boolean;
  title: string;
  message: string;
}

export interface WorkspaceState {
  reference: FolderFile[];
  candidate: FolderFile[];
  referenceLabel: string;
  candidateLabel: string;
  format: string;
  jobId: string | null;
  alert: AlertState;
}

export const initialWorkspaceState: WorkspaceState = {
  reference: [],
  candidate: [],
  referenceLabel: '',
  candidateLabel: '',
  format: 'native',
  jobId: null,
  alert: { open: false, title: '', message: '' },
};

export type WorkspaceAction =
  | { type: 'setReference'; files: FolderFile[]; label: string }
  | { type: 'setCandidate'; files: FolderFile[]; label: string }
  | { type: 'setFormat'; format: string }
  | { type: 'setJob'; jobId: string }
  | { type: 'resetJob' }
  | { type: 'openAlert'; title: string; message: string }
  | { type: 'closeAlert' };

// Changing either folder invalidates any in-flight/finished job.
export function workspaceReducer(state: WorkspaceState, action: WorkspaceAction): WorkspaceState {
  switch (action.type) {
    case 'setReference':
      return { ...state, reference: action.files, referenceLabel: action.label, jobId: null };
    case 'setCandidate':
      return { ...state, candidate: action.files, candidateLabel: action.label, jobId: null };
    case 'setFormat':
      return { ...state, format: action.format };
    case 'setJob':
      return { ...state, jobId: action.jobId };
    case 'resetJob':
      return { ...state, jobId: null };
    case 'openAlert':
      return { ...state, alert: { open: true, title: action.title, message: action.message } };
    case 'closeAlert':
      return { ...state, alert: { ...state.alert, open: false } };
    default:
      return state;
  }
}
