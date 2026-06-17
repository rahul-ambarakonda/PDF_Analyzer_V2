interface ModalProps {
  open: boolean;
  title: string;
  message: string;
  onClose: () => void;
}

/** Simple accessible alert dialog (reuses the existing modal CSS). */
export function Modal({ open, title, message, onClose }: ModalProps) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="modal-actions">
          <button type="button" className="primary-button" onClick={onClose}>
            OK
          </button>
        </div>
      </div>
    </div>
  );
}
