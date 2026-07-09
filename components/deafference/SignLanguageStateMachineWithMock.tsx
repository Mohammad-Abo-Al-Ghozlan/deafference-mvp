// components/deafference/SignLanguageStateMachineWithMock.tsx
'use client';

import React, { useState, useReducer, ReactNode, useEffect, useRef } from 'react';
import { useMockEventGenerator } from '@/hooks/useMockEventGenerator';
import { MockEvent, SignRecognizedPayload, SignDiscardedPayload } from '@/types/mock-events';
import styles from './SignLanguageStateMachine.module.css';

// ============================================================================
// State Machine Types (from original SignLanguageStateMachine)
// ============================================================================

type AppState =
  | 'permission_needed'
  | 'loading_model'
  | 'listening'
  | 'sign_recognized'
  | 'speaking'
  | 'error';

interface StateContext {
  errorMessage?: string;
  recognizedSign?: string;
  confidence?: number;
}

interface StateAction {
  type: 'TRANSITION_TO' | 'SET_ERROR' | 'SET_RECOGNIZED_SIGN' | 'RESET';
  payload?: {
    state?: AppState;
    errorMessage?: string;
    recognizedSign?: string;
    confidence?: number;
  };
}

interface StateProviderState {
  current: AppState;
  context: StateContext;
}

// ============================================================================
// Reducer
// ============================================================================

const stateReducer = (
  state: StateProviderState,
  action: StateAction
): StateProviderState => {
  switch (action.type) {
    case 'TRANSITION_TO': {
      const nextState = action.payload?.state || state.current;
      return {
        current: nextState,
        context: {
          ...state.context,
          errorMessage: undefined,
        },
      };
    }
    case 'SET_ERROR': {
      return {
        current: 'error',
        context: {
          ...state.context,
          errorMessage: action.payload?.errorMessage || 'An error occurred',
        },
      };
    }
    case 'SET_RECOGNIZED_SIGN': {
      return {
        current: 'sign_recognized',
        context: {
          ...state.context,
          recognizedSign: action.payload?.recognizedSign || 'Unknown',
          confidence: action.payload?.confidence || 0,
        },
      };
    }
    case 'RESET': {
      return {
        current: 'permission_needed',
        context: {},
      };
    }
    default:
      return state;
  }
};

// ============================================================================
// Sub-Components (UI Screens)
// ============================================================================

const PermissionNeededScreen: React.FC<{
  onGrantPermission: () => void;
}> = ({ onGrantPermission }) => (
  <div className={styles.screenContainer}>
    <div className={styles.contentBox}>
      <div className={styles.icon}>🎥</div>
      <h2 className={styles.heading}>Camera Permission Required</h2>
      <p className={styles.description}>
        The sign language recognition system needs access to your camera to detect and translate signs in real-time.
      </p>
      <div className={styles.benefits}>
        <ul>
          <li>Real-time sign language translation</li>
          <li>Accurate gesture recognition</li>
          <li>Privacy-first processing</li>
        </ul>
      </div>
      <button
        onClick={onGrantPermission}
        className={styles.primaryButton}
      >
        Grant Camera Permission
      </button>
    </div>
  </div>
);

const LoadingModelScreen: React.FC = () => (
  <div className={styles.screenContainer}>
    <div className={styles.contentBox}>
      <div className={styles.spinnerContainer}>
        <div className={styles.spinner} />
      </div>
      <h2 className={styles.heading}>Initializing ML Model</h2>
      <p className={styles.description}>
        Loading the sign language recognition model. This may take a moment...
      </p>
      <div className={styles.progressBar}>
        <div className={styles.progressFill} />
      </div>
    </div>
  </div>
);

const ListeningScreen: React.FC = () => (
  <div className={styles.screenContainer}>
    <div className={styles.contentBox}>
      <div className={styles.cameraPlaceholder}>
        <div className={styles.scanningOverlay} />
        <div className={styles.cameraFrame} />
        <p className={styles.cameraLabel}>Camera Feed (Mock)</p>
      </div>
      <h2 className={styles.heading}>Listening for Signs</h2>
      <p className={styles.description}>
        Perform your sign in front of the camera. The system will recognize and translate your gestures.
      </p>
      <div className={styles.listeningIndicator}>
        <span className={styles.dot} />
        <span className={styles.listeningText}>Actively listening...</span>
      </div>
    </div>
  </div>
);

const SignRecognizedScreen: React.FC<{
  recognizedSign: string | undefined;
  confidence: number | undefined;
  onSpeakClick: () => void;
}> = ({ recognizedSign, confidence, onSpeakClick }) => (
  <div className={styles.screenContainer}>
    <div className={styles.contentBox}>
      <div className={styles.resultBox}>
        <h2 className={styles.heading}>Sign Recognized!</h2>
        <div className={styles.recognizedText}>
          {recognizedSign || 'Unknown Sign'}
        </div>
        {confidence !== undefined && (
          <div className={styles.confidenceDisplay}>
            Confidence: {(confidence * 100).toFixed(1)}%
          </div>
        )}
        <p className={styles.description}>
          The system has detected and translated your gesture.
        </p>
      </div>
      <button
        onClick={onSpeakClick}
        className={styles.primaryButton}
      >
        Speak This Text
      </button>
      <button className={styles.secondaryButton}>
        Try Another Sign
      </button>
    </div>
  </div>
);

const SpeakingScreen: React.FC = () => (
  <div className={styles.screenContainer}>
    <div className={styles.contentBox}>
      <div className={styles.audioWaveContainer}>
        <div className={styles.waveBar} style={{ animationDelay: '0s' }} />
        <div className={styles.waveBar} style={{ animationDelay: '0.1s' }} />
        <div className={styles.waveBar} style={{ animationDelay: '0.2s' }} />
        <div className={styles.waveBar} style={{ animationDelay: '0.3s' }} />
        <div className={styles.waveBar} style={{ animationDelay: '0.4s' }} />
      </div>
      <h2 className={styles.heading}>Text-to-Speech</h2>
      <p className={styles.description}>
        Converting recognized sign to audio. Please listen...
      </p>
      <div className={styles.speakerIcon}>🔊</div>
    </div>
  </div>
);

const ErrorScreen: React.FC<{
  errorMessage: string | undefined;
  onRetry: () => void;
}> = ({ errorMessage, onRetry }) => (
  <div className={styles.screenContainer}>
    <div className={styles.contentBox}>
      <div className={styles.errorIcon}>⚠️</div>
      <h2 className={styles.heading}>Error Occurred</h2>
      <p className={styles.description}>
        {errorMessage || 'An unexpected error has occurred.'}
      </p>
      <div className={styles.errorDetails}>
        <p>Please check your setup and try again.</p>
      </div>
      <button
        onClick={onRetry}
        className={styles.primaryButton}
      >
        Retry
      </button>
    </div>
  </div>
);

// ============================================================================
// Main Component with Mock Event Generator Integration
// ============================================================================

interface SignLanguageStateMachineWithMockProps {
  mockIntervalMs?: number;
  autoStartMock?: boolean;
}

const SignLanguageStateMachineWithMock: React.FC<
  SignLanguageStateMachineWithMockProps
> = ({ mockIntervalMs = 3500, autoStartMock = false }) => {
  const [state, dispatch] = useReducer(stateReducer, {
    current: 'permission_needed',
    context: {},
  });

  const [mockEventLog, setMockEventLog] = useState<MockEvent[]>([]);
  const errorTimerRef = useRef<NodeJS.Timeout | null>(null);
  const errorCountRef = useRef<number>(0);
  const [errorTrigger, setErrorTrigger] = useState<number>(0);

  /**
   * Auto-recover from error state after 3 seconds
   * Uses errorTrigger to force re-run even when state.current stays 'error'
   */
  useEffect(() => {
    if (state.current === 'error') {
      // Clear any existing timer
      if (errorTimerRef.current) {
        clearTimeout(errorTimerRef.current);
      }

      // Set a new recovery timer
      errorTimerRef.current = setTimeout(() => {
        dispatch({ type: 'TRANSITION_TO', payload: { state: 'listening' } });
        errorTimerRef.current = null;
      }, 3000);
    } else {
      // Clear timer if leaving error state
      if (errorTimerRef.current) {
        clearTimeout(errorTimerRef.current);
        errorTimerRef.current = null;
      }
    }

    return () => {
      if (errorTimerRef.current) {
        clearTimeout(errorTimerRef.current);
      }
    };
  }, [state.current, errorTrigger]);

  /**
   * Handle incoming mock events from the generator
   */
  const handleMockEvent = (event: MockEvent): void => {
    setMockEventLog((prev) => [...prev.slice(-9), event]);

    if (event.type === 'SIGN_RECOGNIZED') {
      const payload = event.payload as SignRecognizedPayload;
      dispatch({
        type: 'SET_RECOGNIZED_SIGN',
        payload: {
          recognizedSign: payload.label,
          confidence: payload.confidence,
        },
      });
    } else if (event.type === 'SIGN_DISCARDED') {
      const payload = event.payload as SignDiscardedPayload;
      dispatch({
        type: 'SET_ERROR',
        payload: {
          errorMessage: `Sign discarded: ${payload.reason} (confidence: ${(payload.confidence * 100).toFixed(1)}%)`,
        },
      });
      // Trigger effect to reset the error recovery timer
      setErrorTrigger((prev) => prev + 1);
    }
  };

  /**
   * Initialize mock event generator
   */
  const { isSimulating, toggleSimulation, eventCount } = useMockEventGenerator({
    intervalMs: mockIntervalMs,
    onEvent: handleMockEvent,
    autoStart: autoStartMock,
  });

  // State transition handlers
  const handleTransition = (nextState: AppState): void => {
    dispatch({ type: 'TRANSITION_TO', payload: { state: nextState } });
  };

  const handleReset = (): void => {
    dispatch({ type: 'RESET' });
  };

  // Render current state
  const renderScreen = (): ReactNode => {
    switch (state.current) {
      case 'permission_needed':
        return (
          <PermissionNeededScreen
            onGrantPermission={() => handleTransition('loading_model')}
          />
        );
      case 'loading_model':
        return <LoadingModelScreen />;
      case 'listening':
        return <ListeningScreen />;
      case 'sign_recognized':
        return (
          <SignRecognizedScreen
            recognizedSign={state.context.recognizedSign}
            confidence={state.context.confidence}
            onSpeakClick={() => handleTransition('speaking')}
          />
        );
      case 'speaking':
        return <SpeakingScreen />;
      case 'error':
        return (
          <ErrorScreen
            errorMessage={state.context.errorMessage}
            onRetry={() => handleTransition('listening')}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className={styles.stateMachineContainer}>
      {renderScreen()}

      {/* Debug Control Panel */}
      <div className={styles.debugPanel}>
        <h3 className={styles.debugTitle}>State Machine Debug Panel (with Mock Events)</h3>
        <div className={styles.debugButtons}>
          <button
            onClick={() => handleTransition('permission_needed')}
            className={`${styles.debugButton} ${
              state.current === 'permission_needed' ? styles.active : ''
            }`}
          >
            Permission Needed
          </button>
          <button
            onClick={() => handleTransition('loading_model')}
            className={`${styles.debugButton} ${
              state.current === 'loading_model' ? styles.active : ''
            }`}
          >
            Loading Model
          </button>
          <button
            onClick={() => handleTransition('listening')}
            className={`${styles.debugButton} ${
              state.current === 'listening' ? styles.active : ''
            }`}
          >
            Listening
          </button>
          <button
            onClick={() => handleReset()}
            className={styles.debugButton}
          >
            Reset
          </button>
        </div>

        {/* Mock Event Generator Controls */}
        <div className={styles.mockControlsPanel}>
          <h4 className={styles.mockControlsTitle}>Mock Event Generator</h4>
          <div className={styles.mockControls}>
            <button
              onClick={toggleSimulation}
              className={`${styles.mockToggleButton} ${
                isSimulating ? styles.mockActive : ''
              }`}
            >
              {isSimulating ? '⏸ Stop Mock Events' : '▶ Start Mock Events'}
            </button>
            <div className={styles.mockStats}>
              <span className={styles.mockStatLabel}>Status:</span>
              <span className={styles.mockStatValue}>
                {isSimulating ? '🟢 Running' : '🔴 Stopped'}
              </span>
              <span className={styles.mockStatLabel}>Events:</span>
              <span className={styles.mockStatValue}>{eventCount}</span>
            </div>
          </div>

          {/* Recent Mock Events Log */}
          {mockEventLog.length > 0 && (
            <div className={styles.eventLog}>
              <h5 className={styles.eventLogTitle}>Recent Events</h5>
              <div className={styles.eventLogList}>
                {mockEventLog.map((event, index) => (
                  <div key={index} className={styles.eventLogItem}>
                    <span className={styles.eventType}>
                      {event.type === 'SIGN_RECOGNIZED' ? '✓' : '✗'}
                    </span>
                    <span className={styles.eventDetail}>
                      {event.type === 'SIGN_RECOGNIZED'
                        ? `${(event.payload as SignRecognizedPayload).label} (${((event.payload as SignRecognizedPayload).confidence * 100).toFixed(0)}%)`
                        : `Discarded: ${(event.payload as SignDiscardedPayload).reason}`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className={styles.currentStateDisplay}>
          <span>Current State:</span>
          <strong>{state.current}</strong>
        </div>
      </div>
    </div>
  );
};

export default SignLanguageStateMachineWithMock;
