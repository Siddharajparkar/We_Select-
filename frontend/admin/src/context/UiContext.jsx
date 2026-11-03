import { createContext, useCallback, useContext, useRef, useState } from 'react';
import Modal from '../components/Modal.jsx';

const UiCtx = createContext(null);

export function UiProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const [dialog, setDialog] = useState(null);
  const idRef = useRef(0);

  const toast = useCallback((message, type = 'info') => {
    const id = ++idRef.current;
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);

  // confirm({title, message, confirmText, danger}) -> Promise<boolean>
  const confirm = useCallback(
    (opts) => new Promise((resolve) => setDialog({ ...opts, resolve })),
    []
  );

  const close = (value) => {
    dialog.resolve(value);
    setDialog(null);
  };

  return (
    <UiCtx.Provider value={{ toast, confirm }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>{t.message}</div>
        ))}
      </div>
      {dialog && (
        <Modal
          title={dialog.title || 'Please confirm'}
          onClose={() => close(false)}
          size="sm"
          footer={
            <>
              <button className="btn btn-ghost" onClick={() => close(false)}>Cancel</button>
              <button
                className={`btn ${dialog.danger ? 'btn-danger' : 'btn-primary'}`}
                onClick={() => close(true)}
              >
                {dialog.confirmText || 'Confirm'}
              </button>
            </>
          }
        >
          <p>{dialog.message}</p>
        </Modal>
      )}
    </UiCtx.Provider>
  );
}

export const useUi = () => useContext(UiCtx);

