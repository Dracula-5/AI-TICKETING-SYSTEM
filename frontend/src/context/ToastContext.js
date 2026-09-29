import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { Snackbar, Alert } from "@mui/material";

// Default value doubles as the fallback for anything rendered outside the
// provider (e.g. component tests that mount a page directly) -- calling
// toast.error()/success() just becomes a no-op instead of crashing.
const ToastContext = createContext({
  showToast: () => {},
  success: () => {},
  error: () => {},
  info: () => {},
});

export function ToastProvider({ children }) {
  const [current, setCurrent] = useState(null);
  const [open, setOpen] = useState(false);
  const queueRef = useRef([]);

  const processQueue = useCallback(() => {
    if (queueRef.current.length > 0) {
      setCurrent(queueRef.current.shift());
      setOpen(true);
    } else {
      setCurrent(null);
    }
  }, []);

  const showToast = useCallback((message, severity = "info") => {
    queueRef.current.push({ message, severity, key: Date.now() + Math.random() });
    setOpen((isOpen) => {
      if (isOpen) {
        // Close the current one first; onExited will pull the next from the queue.
        return false;
      }
      processQueue();
      return isOpen;
    });
  }, [processQueue]);

  const handleClose = useCallback((_event, reason) => {
    if (reason === "clickaway") return;
    setOpen(false);
  }, []);

  const value = useMemo(() => ({
    showToast,
    success: (message) => showToast(message, "success"),
    error: (message) => showToast(message, "error"),
    info: (message) => showToast(message, "info"),
  }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <Snackbar
        key={current?.key}
        open={open}
        autoHideDuration={5000}
        onClose={handleClose}
        TransitionProps={{ onExited: processQueue }}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        {current ? (
          <Alert onClose={handleClose} severity={current.severity} variant="filled" sx={{ width: "100%" }}>
            {current.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
