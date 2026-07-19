import { useEffect, useState } from "react";


export function useTransientNotice(timeoutMs = 5_000) {
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = window.setTimeout(() => setNotice(null), timeoutMs);
    return () => window.clearTimeout(timer);
  }, [notice, timeoutMs]);

  return [notice, setNotice] as const;
}
