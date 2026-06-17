import { FormatSelect } from '@/components/ui/FormatSelect';
import { StatusPill } from '@/components/ui/StatusPill';
import { NATIVE_FORMATS } from '@/lib/formats';
import { FolderPicker } from '@/features/comparison/FolderPicker';
import type { FolderFile } from '@/types';

interface SourcePanelProps {
  format: string;
  onFormatChange: (value: string) => void;
  referenceCount: number;
  candidateCount: number;
  hasReport: boolean;
  isProcessing: boolean;
  canGenerate: boolean;
  statusText: string;
  statusOk: boolean;
  onSelectReference: (files: FolderFile[], label: string) => void;
  onSelectCandidate: (files: FolderFile[], label: string) => void;
  onInvalid: (message: string) => void;
  onGenerate: () => void;
}

export function SourcePanel(props: SourcePanelProps) {
  const selectedFormatLabel =
    NATIVE_FORMATS.find((f) => f.value === props.format)?.label ?? props.format;

  return (
    <div className="panel configure-panel" style={{ marginBottom: 24 }}>
      <div className="panel-header">
        <div>
          <p className="panel-kicker">Step 1</p>
          <h2>Configure source</h2>
        </div>
        <FormatSelect value={props.format} onChange={props.onFormatChange} />
      </div>

      <div className="run-grid run-grid-single">
        <div className="run-card">
          <div className="run-card-title">
            <span className="run-num">1</span>
            <h3>Compare reference vs Creo</h3>
            <span className="run-card-status">
              <StatusPill tone={props.hasReport ? 'done' : 'wait'}>
                {props.hasReport ? 'Completed' : 'Pending'}
              </StatusPill>
            </span>
          </div>

          <FolderPicker
            label="PDF files (reference)"
            count={props.referenceCount}
            promptText="Click to select reference PDFs"
            emptyHint="No files selected yet · up to 20 PDFs"
            onSelect={props.onSelectReference}
            onInvalid={props.onInvalid}
          />

          <FolderPicker
            label="Creo PDF files"
            count={props.candidateCount}
            promptText="Click to select Creo PDFs"
            emptyHint="No files selected yet · up to 20 PDFs"
            onSelect={props.onSelectCandidate}
            onInvalid={props.onInvalid}
          />

          <button
            type="button"
            className="generate-button"
            disabled={!props.canGenerate}
            onClick={props.onGenerate}
          >
            {props.isProcessing ? (
              <>
                <span className="btn-spinner" />
                <span>Analyzing drawings…</span>
              </>
            ) : (
              <>Generate report →</>
            )}
          </button>
        </div>
      </div>

      <div className="status-row">
        <div className="status-cell">
          <span>Selected Format</span>
          <strong>{selectedFormatLabel}</strong>
        </div>
        <div className="status-cell">
          <span>Status</span>
          <strong className={props.statusOk ? 'status-ok' : ''}>{props.statusText}</strong>
        </div>
      </div>
    </div>
  );
}
