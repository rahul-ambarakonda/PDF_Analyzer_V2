import { useEffect, useRef, useState } from 'react';

import { NATIVE_FORMATS } from '@/lib/formats';

interface FormatSelectProps {
  value: string;
  onChange: (value: string) => void;
}

/**
 * Presentational source-format selector. Cosmetic only — the comparator operates on the uploaded
 * PDFs and does not consume this value; kept to preserve the original workspace design.
 */
export function FormatSelect({ value, onChange }: FormatSelectProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selectedLabel = NATIVE_FORMATS.find((f) => f.value === value)?.label ?? value;

  useEffect(() => {
    const onPointerDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('pointerdown', onPointerDown);
    return () => window.removeEventListener('pointerdown', onPointerDown);
  }, []);

  return (
    <div style={{ minWidth: 200 }} ref={ref}>
      <div className="custom-select">
        <button type="button" className="custom-select-trigger" onClick={() => setOpen((o) => !o)}>
          <span>{selectedLabel}</span>
          <span className={`caret ${open ? 'open' : ''}`}>▾</span>
        </button>
        {open && (
          <div className="custom-select-menu" role="listbox">
            {NATIVE_FORMATS.map((item) => (
              <button
                key={item.value}
                type="button"
                className={`custom-select-option ${item.value === value ? 'active' : ''}`}
                onClick={() => {
                  onChange(item.value);
                  setOpen(false);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
