import { useState, useRef, useCallback, useEffect } from 'react';

interface UseInactivityTimeoutConfig {
  timeoutSeconds?: number;
  onTimeout?: () => void;
  enabled?: boolean;
  onTickUpdate?: (remaining: number) => void;
}

interface UseInactivityTimeoutReturn {
  isTimedOut: boolean;
  remainingSeconds: number;
  resetTimer: () => void;
  isActive: boolean;
}

export function useInactivityTimeout({
  timeoutSeconds = 10,
  onTimeout,
  enabled = true,
  onTickUpdate,
}: UseInactivityTimeoutConfig): UseInactivityTimeoutReturn {
  const [isTimedOut, setIsTimedOut] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(timeoutSeconds);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const elapsedRef = useRef(0);

  // Keep the latest callbacks in refs so the interval effect does NOT depend on
  // them. Callers usually pass inline arrow functions (new identity each render),
  // which previously tore down and rebuilt the 500ms interval on every tick —
  // causing timer drift. With refs the interval is created once per enabled span.
  const onTimeoutRef = useRef(onTimeout);
  const onTickUpdateRef = useRef(onTickUpdate);
  useEffect(() => {
    onTimeoutRef.current = onTimeout;
    onTickUpdateRef.current = onTickUpdate;
  }, [onTimeout, onTickUpdate]);

  const resetTimer = useCallback(() => {
    elapsedRef.current = 0;
    setRemainingSeconds(timeoutSeconds);
    setIsTimedOut(false);
  }, [timeoutSeconds]);

  useEffect(() => {
    if (!enabled) {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }

    if (isTimedOut) {
      return;
    }

    timerRef.current = setInterval(() => {
      elapsedRef.current += 0.5;
      const remaining = Math.max(0, timeoutSeconds - elapsedRef.current);
      setRemainingSeconds(Math.ceil(remaining));

      onTickUpdateRef.current?.(Math.ceil(remaining));

      if (remaining <= 0) {
        setIsTimedOut(true);
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
        onTimeoutRef.current?.();
      }
    }, 500);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [enabled, isTimedOut, timeoutSeconds]);

  return {
    isTimedOut,
    remainingSeconds,
    resetTimer,
    isActive: enabled && !isTimedOut,
  };
}
