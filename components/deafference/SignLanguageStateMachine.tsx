// components/deafference/SignLanguageStateMachine.tsx
'use client';

import React, { useState, useReducer, ReactNode } from 'react';
import styles from './SignLanguageStateMachine.module.css';

// Type definitions
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
}

interface StateAction {
  type: 'TRANSITION_TO' | 'SET_ERROR' | 'SET_RECOGNIZED_SIGN' | 'RESET';
  payload?: {
    state?: AppState;
    errorMessage?: string;
    recognizedSign?: string;
  };
}

interface StateProviderState {
  current: AppState;
  context: StateContext;
}

// Reducer function
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

// Sub-components for each state

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
        <p className={styles.cameraLabel}>Camera Feed</p>
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
  onSpeakClick: () => void;
}> = ({ recognizedSign, onSpeakClick }) => (
  <div className={styles.screenContainer}>
    <div className={styles.contentBox}>
      <div className={styles.resultBox}>
        <h2 className={styles.heading}>Sign Recognized!</h2>
        <div className={styles.recognizedText}>
          {recognizedSign || 'Unknown Sign'}
        </div>
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

// Main component
const SignLanguageStateMachine: React.FC = () => {
  const [state, dispatch] = useReducer(stateReducer, {
    current: 'permission_needed',
    context: {},
  });

  const handleTransition = (nextState: AppState): void => {
    dispatch({ type: 'TRANSITION_TO', payload: { state: nextState } });
  };

  const handleError = (message: string): void => {
    dispatch({ type: 'SET_ERROR', payload: { errorMessage: message } });
  };

  const handleRecognizedSign = (sign: string): void => {
    dispatch({
      type: 'SET_RECOGNIZED_SIGN',
      payload: { recognizedSign: sign },
    });
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
            onSpeakClick={() => handleTransition('speaking')}
          />
        );
      case 'speaking':
        return <SpeakingScreen />;
      case 'error':
        return (
          <ErrorScreen
            errorMessage={state.context.errorMessage}
            onRetry={() => handleTransition('permission_needed')}
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
        <h3 className={styles.debugTitle}>State Machine Debug Panel</h3>
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
            onClick={() => handleRecognizedSign('Hello')}
            className={`${styles.debugButton} ${
              state.current === 'sign_recognized' ? styles.active : ''
            }`}
          >
            Sign Recognized
          </button>
          <button
            onClick={() => handleTransition('speaking')}
            className={`${styles.debugButton} ${
              state.current === 'speaking' ? styles.active : ''
            }`}
          >
            Speaking
          </button>
          <button
            onClick={() =>
              handleError(
                'Camera access denied. Please check your permissions.'
              )
            }
            className={`${styles.debugButton} ${styles.errorButton} ${
              state.current === 'error' ? styles.active : ''
            }`}
          >
            Trigger Error
          </button>
          <button
            onClick={handleReset}
            className={styles.debugButton}
          >
            Reset
          </button>
        </div>
        <div className={styles.currentStateDisplay}>
          <span>Current State:</span>
          <strong>{state.current}</strong>
        </div>
      </div>
    </div>
  );
};

export default SignLanguageStateMachine;
