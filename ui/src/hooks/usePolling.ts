import { useEffect, useRef, type DependencyList } from 'react';

const POLL_INTERVAL_MS = 4000;

export function usePolling(
  active: boolean,
  tick: (isMounted: () => boolean) => Promise<void>,
  deps: DependencyList
): void {
  const tickRef = useRef(tick);
  tickRef.current = tick;
  useEffect(() => {
    if (!active) return;
    let alive = true;
    const isMounted = () => alive;
    const run = async () => {
      await tickRef.current(isMounted);
    };
    void run();
    const timer = window.setInterval(() => void run(), POLL_INTERVAL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
    // tick is read from tickRef each interval; deps list matches prior effects.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, ...deps]);
}
