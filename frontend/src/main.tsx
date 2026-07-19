import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { I18nProvider } from "./i18n/I18nProvider";
import "./styles.css";

declare global {
  interface Window {
    __consoleErrors: string[];
  }
}

window.__consoleErrors = [];
window.addEventListener("error", (event) => window.__consoleErrors.push(String(event.message)));
window.addEventListener("unhandledrejection", (event) => window.__consoleErrors.push(String(event.reason)));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <I18nProvider>
          <App />
        </I18nProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
