import { Alert, Snackbar } from "@mui/material";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Severity = "success" | "error" | "info" | "warning";
interface ToastState {
  message: string;
  severity: Severity;
  key: number;
}

const ToastContext = createContext<(message: string, severity?: Severity) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const show = useCallback((message: string, severity: Severity = "success") => {
    setToast({ message, severity, key: Date.now() });
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <Snackbar
        key={toast?.key}
        open={!!toast}
        autoHideDuration={toast?.severity === "error" ? 7000 : 4000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        {toast ? (
          <Alert severity={toast.severity} variant="filled" onClose={() => setToast(null)} sx={{ minWidth: 280 }}>
            {toast.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
