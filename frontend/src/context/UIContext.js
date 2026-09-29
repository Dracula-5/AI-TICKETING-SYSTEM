import { createContext, useContext, useMemo, useState } from "react";

// Default value doubles as the fallback for anything rendered outside the
// provider (e.g. component tests that mount a page directly) -- the hamburger
// button and mobile drawer just become no-ops instead of crashing.
const UIContext = createContext({
  mobileNavOpen: false,
  setMobileNavOpen: () => {},
});

export function UIProvider({ children }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const value = useMemo(() => ({ mobileNavOpen, setMobileNavOpen }), [mobileNavOpen]);
  return <UIContext.Provider value={value}>{children}</UIContext.Provider>;
}

export function useUI() {
  return useContext(UIContext);
}
