'use client';

import { useReducer, useCallback, useRef, useEffect, useState } from 'react';
import { useMockEventGenerator } from '@/hooks/useMockEventGenerator';
import { useInactivityTimeout } from '@/hooks/useInactivityTimeout';
import { useTensorFlowModel } from '@/hooks/useTensorFlowModel';
import CameraDeniedScreen from './CameraDeniedScreen';
import BrowserUnsupportedScreen from './BrowserUnsupportedScreen';
import NoSignsDetectedScreen from './NoSignsDetectedScreen';
import ModelLoadErrorFallback from './ModelLoadErrorFallback';
import LoadingSpinner from './LoadingSpinner';
import styles from './ErrorScreens.module.css';

type AppState =
  | 'permission_needed'
  | 'loading_model'
  | 'listening'
  | 'sign_recognized'
  | 'speaking'
  | 'error'
  | 'camera_denied'
  | 'browser_unsupported'
  | 'no_signs_detected';

interface StateAction {
  type: string;
  payload?: any;
}

interface ComponentProps {
  mockIntervalMs?: number;
  autoStartMock?: boolean;
  inactivityTimeoutSeconds?: number;
  onStateChange?: (state: AppState) => void;
}

function reducer(state: AppState, action: StateAction): AppState {
  switch (action.type) {
    case 'TRANSITION_TO':
      return action.payload.state;
    case 'SET_CAMERA_DENIED':
      return 'camera_denied';
    case 'SET_BROWSER_UNSUPPORTED':
      return 'browser_unsupported';
    case 'SET_NO_SIGNS_DETECTED':
      return 'no_signs_detected';
    default:
      return state;
  }
}

const stateDescriptions: Record<AppState, string> = {
  permission_needed: '🔐 Requesting Camera Permission',
  loading_model: '⏳ Loading ML Model',
  listening: '👂 Listening for ASL Signs',
  sign_recognized: '✓ Sign Recognized',
  speaking: '🔊 Speaking Text',
  error: '⚠️ Error Detected',
  camera_denied: '🚫 Camera Access Denied',
  browser_unsupported: '❌ Browser Not Supported',
  no_signs_detected: '👋 Inactivity Timeout',
};

export default function EnhancedSignLanguageStateMachine({
  mockIntervalMs = 3500,
  autoStartMock = false,
  inactivityTimeoutSeconds = 10,
  onStateChange,
}: ComponentProps) {
  const [state, dispatch] = useReducer(reducer, 'permission_needed');
  const recognizedSignRef = useRef<{ text: string; confidence: number } | null>(null);
  const lastEventRef = useRef<string>('');

  // Initialize TensorFlow.js and prediction engine (Stage 2)
  // hasError/errorMessage/retry (KAN-14+): timeout + failure fallback handling
  const { isModelLoading, isModelReady, hasError, errorMessage, predictionEngine, retry } =
    useTensorFlowModel();

  // When the model fails to load, the user can choose to fall back to the
  // Stage 1 mock event generator instead of being blocked entirely.
  const [isMockMode, setIsMockMode] = useState(false);

  // Debug-only override so the failure/timeout screen can be exercised without
  // a real network failure (the mock TF.js engine otherwise never fails).
  const [debugForceError, setDebugForceError] = useState(false);
  const effectiveHasError = hasError || debugForceError;
  const effectiveErrorMessage = hasError
    ? errorMessage
    : debugForceError
      ? 'Simulated failure: network timeout while fetching model weights.'
      : null;

  const handleContinueInMockMode = useCallback(() => {
    setIsMockMode(true);
  }, []);

  const handleRetryModelLoad = useCallback(() => {
    setIsMockMode(false);
    setDebugForceError(false);
    retry();
  }, [retry]);

  const handleMockEvent = useCallback(
    (event: any) => {
      if (event.type === 'SIGN_RECOGNIZED') {
        recognizedSignRef.current = {
          text: event.payload.predictedLabel,
          confidence: event.payload.confidence,
        };
        dispatch({ type: 'TRANSITION_TO', payload: { state: 'sign_recognized' } });
      } else if (event.type === 'SIGN_DISCARDED') {
        dispatch({ type: 'TRANSITION_TO', payload: { state: 'error' } });
      }
      lastEventRef.current = event.type;
    },
    []
  );

  const { isSimulating, startSimulation, stopSimulation, eventCount } =
    useMockEventGenerator({
      intervalMs: mockIntervalMs,
      onEvent: handleMockEvent,
      autoStart: autoStartMock,
    });

  const { remainingSeconds, resetTimer: resetInactivityTimer } =
    useInactivityTimeout({
      timeoutSeconds: inactivityTimeoutSeconds,
      enabled: state === 'listening',
      onTimeout: () => {
        dispatch({
          type: 'TRANSITION_TO',
          payload: { state: 'no_signs_detected' },
        });
      },
    });

  const transitionState = useCallback(
    (newState: AppState) => {
      dispatch({ type: 'TRANSITION_TO', payload: { state: newState } });
      if (onStateChange) {
        onStateChange(newState);
      }
    },
    [onStateChange]
  );

  /**
   * Stage 2 Integration: Wire TensorFlow.js model lifecycle into state machine
   * When model is ready, automatically transition from loading_model to listening
   */
  useEffect(() => {
    if (state === 'loading_model' && ((isModelReady && !isModelLoading) || isMockMode)) {
      // Model initialization complete (or the user opted into mock mode), safe to start listening
      transitionState('listening');
    }
  }, [state, isModelReady, isModelLoading, isMockMode, transitionState]);

  const handlePermissionRequest = () => {
    transitionState('loading_model');
  };

  const handleRetry = () => {
    transitionState('listening');
    resetInactivityTimer();
  };

  const handleKeepListening = () => {
    resetInactivityTimer();
    transitionState('listening');
  };

  return (
    <div className={styles.errorScreenContainer}>
      <div className={styles.errorScreen}>
        {/* State Display */}
        <div style={{ marginBottom: '2rem', textAlign: 'center' }}>
          <div
            style={{
              fontSize: '2rem',
              marginBottom: '0.5rem',
              animation: 'pulse 2s infinite',
            }}
          >
            {stateDescriptions[state].split(' ')[0]}
          </div>
          <h2 style={{ color: '#f1f5f9', margin: '0' }}>
            {stateDescriptions[state]}
          </h2>
        </div>

        {/* State Renderers */}
        {state === 'permission_needed' && (
          <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
            <p style={{ color: '#cbd5e1', marginBottom: '1rem' }}>
              This app requires camera access to recognize ASL signs. Please grant permission to continue.
            </p>
            <button
              className={`${styles.button} ${styles.primaryButton}`}
              onClick={handlePermissionRequest}
            >
              Grant Camera Permission
            </button>
          </div>
        )}

        {state === 'loading_model' && (
          <div style={{ marginTop: '-1rem', marginBottom: '-1rem', marginLeft: '-1rem', marginRight: '-1rem' }}>
            {effectiveHasError ? (
              <ModelLoadErrorFallback
                errorMessage={effectiveErrorMessage ?? 'Unknown error while initializing the model.'}
                onRetry={handleRetryModelLoad}
                onContinueMockMode={handleContinueInMockMode}
              />
            ) : (
              <div style={{ padding: '1rem 1rem 2rem' }}>
                <LoadingSpinner
                  label={isModelLoading ? 'Loading model engine...' : 'Preparing prediction engine...'}
                />
                <button
                  className={`${styles.button} ${styles.secondaryButton}`}
                  onClick={() => setDebugForceError(true)}
                  style={{ marginTop: '1rem' }}
                >
                  🧪 Simulate Model Load Failure
                </button>
              </div>
            )}
          </div>
        )}

        {state === 'listening' && (
          <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
            <p style={{ color: '#cbd5e1', marginBottom: '1rem' }}>
              Monitoring your hands for sign language...
            </p>
            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
              <button
                className={`${styles.button} ${isSimulating ? styles.secondaryButton : styles.primaryButton}`}
                onClick={isSimulating ? stopSimulation : startSimulation}
              >
                {isSimulating ? 'Stop Mock Events' : 'Start Mock Events'}
              </button>
            </div>
            <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginTop: '1rem' }}>
              Events generated: {eventCount}
            </p>
          </div>
        )}

        {state === 'sign_recognized' && recognizedSignRef.current && (
          <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
            <p style={{ color: '#22c55e', fontSize: '1.25rem', fontWeight: 'bold' }}>
              ✓ {recognizedSignRef.current.text}
            </p>
            <p style={{ color: '#cbd5e1', marginBottom: '1rem' }}>
              Confidence: {(recognizedSignRef.current.confidence * 100).toFixed(1)}%
            </p>
            <button
              className={`${styles.button} ${styles.primaryButton}`}
              onClick={() => transitionState('speaking')}
            >
              Speak This Text
            </button>
            <button
              className={`${styles.button} ${styles.secondaryButton}`}
              onClick={() => {
                transitionState('listening');
                resetInactivityTimer();
              }}
              style={{ marginTop: '0.5rem' }}
            >
              Try Another
            </button>
          </div>
        )}

        {state === 'speaking' && (
          <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
            <div style={{ fontSize: '2rem', marginBottom: '1rem', animation: 'pulse 2s infinite' }}>
              🔊
            </div>
            <p style={{ color: '#cbd5e1', marginBottom: '1rem' }}>
              Playing audio...
            </p>
            <button
              className={`${styles.button} ${styles.primaryButton}`}
              onClick={() => {
                transitionState('listening');
                resetInactivityTimer();
              }}
            >
              Back to Listening
            </button>
          </div>
        )}

        {state === 'error' && (
          <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
            <p style={{ color: '#fca5a5', marginBottom: '1rem' }}>
              Could not recognize sign. Try again.
            </p>
            <button
              className={`${styles.button} ${styles.primaryButton}`}
              onClick={handleRetry}
            >
              Retry
            </button>
          </div>
        )}

        {state === 'camera_denied' && (
          <div style={{ marginTop: '-1rem', marginBottom: '-1rem', marginLeft: '-1rem', marginRight: '-1rem' }}>
            <CameraDeniedScreen onRetry={() => transitionState('loading_model')} />
          </div>
        )}

        {state === 'browser_unsupported' && (
          <div style={{ marginTop: '-1rem', marginBottom: '-1rem', marginLeft: '-1rem', marginRight: '-1rem' }}>
            <BrowserUnsupportedScreen onRetry={() => transitionState('permission_needed')} />
          </div>
        )}

        {state === 'no_signs_detected' && (
          <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
            <p style={{ color: '#cbd5e1', marginBottom: '1rem' }}>
              No signs detected during timeout. Returning to listening state.
            </p>
            <button
              className={`${styles.button} ${styles.primaryButton}`}
              onClick={() => {
                transitionState('listening');
                resetInactivityTimer();
              }}
            >
              Continue Listening
            </button>
          </div>
        )}

        {/* Debug Panel */}
        <div style={{ marginTop: '2rem', paddingTop: '1.5rem', borderTop: '1px solid rgba(148, 163, 184, 0.2)' }}>
          <h3 style={{ color: '#f1f5f9', marginBottom: '1rem', fontSize: '0.9rem' }}>
            DEBUG: Quick State Transitions
          </h3>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: '0.5rem',
            }}
          >
            {(
              [
                'permission_needed',
                'loading_model',
                'listening',
                'sign_recognized',
                'speaking',
                'error',
                'camera_denied',
                'browser_unsupported',
                'no_signs_detected',
              ] as AppState[]
            ).map((s) => (
              <button
                key={s}
                onClick={() => transitionState(s)}
                style={{
                  padding: '0.5rem',
                  fontSize: '0.75rem',
                  background: state === s ? '#3b82f6' : 'rgba(148, 163, 184, 0.1)',
                  color: state === s ? 'white' : '#cbd5e1',
                  border: 'none',
                  borderRadius: '0.25rem',
                  cursor: 'pointer',
                  fontWeight: state === s ? '600' : '400',
                }}
              >
                {s}
              </button>
            ))}
          </div>
          <p style={{ color: '#94a3b8', fontSize: '0.8rem', marginTop: '0.75rem' }}>
            Current State: <strong>{state}</strong> | Inactivity: {remainingSeconds}s
          </p>
        </div>
      </div>

      {/* Inactivity Overlay */}
      {state === 'listening' && (
        <NoSignsDetectedScreen
          onReset={handleKeepListening}
          timeoutSeconds={remainingSeconds}
          showOverlay={remainingSeconds < inactivityTimeoutSeconds && remainingSeconds > 0}
        />
      )}

      <style>{`
        @keyframes slideRight {
          from {
            transform: translateX(-100%);
          }
          to {
            transform: translateX(100%);
          }
        }
      `}</style>
    </div>
  );
}
