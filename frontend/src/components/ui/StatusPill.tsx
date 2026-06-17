import type { ReactNode } from 'react';

export type PillTone = 'done' | 'wait';

export function StatusPill({ tone, children }: { tone: PillTone; children: ReactNode }) {
  return (
    <span className={`status-pill ${tone === 'done' ? 'pill-done' : 'pill-wait'}`}>{children}</span>
  );
}
