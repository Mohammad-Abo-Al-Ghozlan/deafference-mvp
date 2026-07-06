// hooks/useMockEventGenerator.ts
'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import {
  MockEvent,
  MockEventCallback,
  MockEventType,
  MOCK_ASL_VOCABULARY,
  DISCARD_REASONS,
  SignRecognizedPayload,
  SignDiscardedPayload,
} from '@/types/mock-events';

interface UseMockEventGeneratorConfig {
  intervalMs?: number;
  onEvent: MockEventCallback;
  autoStart?: boolean;
}

interface UseMockEventGeneratorReturn {
  isSimulating: boolean;
  startSimulation: () => void;
  stopSimulation: () => void;
  toggleSimulation: () => void;
  eventCount: number;
}

/**
 * Custom React hook for generating mock ML inference events
 * Simulates real-time sign language recognition for testing without a live model
 *
 * @param config - Configuration object with interval, callback, and optional autoStart
 * @returns Object with simulation control methods and current state
 *
 * @example
 * const { isSimulating, toggleSimulation, eventCount } = useMockEventGenerator({
 *   intervalMs: 3500,
 *   onEvent: (event) => {
 *     if (event.type === 'SIGN_RECOGNIZED') {
 *       handleSignRecognized(event.payload);
 *     } else {
 *       handleSignDiscarded(event.payload);
 *     }
 *   },
 *   autoStart: true,
 * });
 */
export const useMockEventGenerator = (
  config: UseMockEventGeneratorConfig
): UseMockEventGeneratorReturn => {
  const {
    intervalMs = 3500,
    onEvent,
    autoStart = false,
  } = config;

  const [isSimulating, setIsSimulating] = useState<boolean>(autoStart);
  const [eventCount, setEventCount] = useState<number>(0);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const lastEventTypeRef = useRef<MockEventType>('SIGN_RECOGNIZED');
  const onEventRef = useRef<MockEventCallback>(onEvent);

  // Keep onEventRef in sync with the latest onEvent callback
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  /**
   * Generates a random confidence score
   * SIGN_RECOGNIZED: 0.75 - 0.99
   * SIGN_DISCARDED: 0.15 - 0.50
   */
  const generateConfidenceScore = (eventType: MockEventType): number => {
    if (eventType === 'SIGN_RECOGNIZED') {
      return Math.random() * (0.99 - 0.75) + 0.75;
    }
    return Math.random() * (0.50 - 0.15) + 0.15;
  };

  /**
   * Generates a random mock event
   * Alternates between SIGN_RECOGNIZED and SIGN_DISCARDED
   */
  const generateMockEvent = (): MockEvent => {
    const eventType: MockEventType =
      lastEventTypeRef.current === 'SIGN_RECOGNIZED'
        ? 'SIGN_DISCARDED'
        : 'SIGN_RECOGNIZED';

    lastEventTypeRef.current = eventType;

    const timestamp = Date.now();
    const confidence = generateConfidenceScore(eventType);

    if (eventType === 'SIGN_RECOGNIZED') {
      const randomLabel =
        MOCK_ASL_VOCABULARY[Math.floor(Math.random() * MOCK_ASL_VOCABULARY.length)];

      const payload: SignRecognizedPayload = {
        label: randomLabel,
        confidence,
        timestamp,
      };

      return {
        type: 'SIGN_RECOGNIZED',
        payload,
      };
    }

    const randomReason =
      DISCARD_REASONS[Math.floor(Math.random() * DISCARD_REASONS.length)];

    const payload: SignDiscardedPayload = {
      reason: randomReason,
      confidence,
      timestamp,
    };

    return {
      type: 'SIGN_DISCARDED',
      payload,
    };
  };

  /**
   * Emits a mock event and increments the counter
   */
  const emitMockEvent = useCallback((): void => {
    const event = generateMockEvent();
    onEventRef.current(event);
    setEventCount((prev) => prev + 1);
  }, []);

  /**
   * Starts the simulation
   */
  const startSimulation = useCallback((): void => {
    if (intervalRef.current !== null) {
      return;
    }

    setIsSimulating(true);

    intervalRef.current = setInterval(() => {
      emitMockEvent();
    }, intervalMs);
  }, [intervalMs, emitMockEvent]);

  /**
   * Stops the simulation
   */
  const stopSimulation = useCallback((): void => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    setIsSimulating(false);
  }, []);

  /**
   * Toggles simulation ON/OFF
   */
  const toggleSimulation = useCallback((): void => {
    if (isSimulating) {
      stopSimulation();
    } else {
      startSimulation();
    }
  }, [isSimulating, startSimulation, stopSimulation]);

  /**
   * Auto-start simulation if configured
   */
  useEffect(() => {
    if (autoStart) {
      startSimulation();
    }

    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [autoStart, startSimulation]);

  return {
    isSimulating,
    startSimulation,
    stopSimulation,
    toggleSimulation,
    eventCount,
  };
};
