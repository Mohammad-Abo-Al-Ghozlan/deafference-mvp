/**
 * Sign Language Recognition Application - State Machine Architecture
 * 
 * A robust, type-safe state machine managing the complete workflow:
 * permission_needed → loading_model → listening → sign_recognized → speaking → error
 */

import React, { useState, useCallback } from 'react';

/**
 * Strict union type for all valid application states
 */
type AppState = 
  | 'permission_needed' 
  | 'loading_model' 
  | 'listening' 
  | 'sign_recognized' 
  | 'speaking' 
  | 'error';

/**
 * Type for state transitions with optional payload data
 */
interface StateTransition {
  state: AppState;
  data?: {
    recognizedSign?: string | null;
    errorMessage?: string | null;
    audioWaveform?: number[];
  };
}

/**
 * Application context data structure
 */
interface AppContextData {
  recognizedSign: string | null;
  errorMessage: string | null;
  audioWaveform: number[];
}

/**
 * ============================================================================
 * STATE COMPONENTS - One functional component per screen
 * ============================================================================
 */

/**
 * PermissionNeededScreen
 * Explains camera requirement and provides grant permission action
 */
interface PermissionNeededScreenProps {
  onGrantPermission: () => void;
}

const PermissionNeededScreen: React.FC<PermissionNeededScreenProps> = ({ 
  onGrantPermission 
}) => {
  return (
    <div className="screen permission-needed-screen" style={styles.screenContainer}>
      <div style={styles.contentContainer}>
        <div style={styles.iconContainer}>
          <span style={styles.largeIcon}>📷</span>
        </div>
        
        <h1 style={styles.screenTitle}>Camera Permission Required</h1>
        
        <p style={styles.screenDescription}>
          To recognize sign language in real-time, this application needs access to your device's camera.
        </p>
        
        <div style={styles.featureList}>
          <div style={styles.featureItem}>
            <span style={styles.checkmark}>✓</span>
            <span>Real-time sign language recognition</span>
          </div>
          <div style={styles.featureItem}>
            <span style={styles.checkmark}>✓</span>
            <span>Instant text-to-speech feedback</span>
          </div>
          <div style={styles.featureItem}>
            <span style={styles.checkmark}>✓</span>
            <span>Your camera feed stays private - only processed locally</span>
          </div>
        </div>
        
        <button 
          onClick={onGrantPermission}
          style={styles.primaryButton}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = '#0056b3';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = '#007bff';
          }}
        >
          Grant Camera Permission
        </button>
        
        <p style={styles.smallText}>
          You can revoke this permission at any time in your browser settings.
        </p>
      </div>
    </div>
  );
};

/**
 * LoadingModelScreen
 * Displays loading spinner with model initialization status
 */
const LoadingModelScreen: React.FC = () => {
  return (
    <div className="screen loading-model-screen" style={styles.screenContainer}>
      <div style={styles.contentContainer}>
        <div style={styles.spinnerContainer}>
          <div style={styles.spinner}></div>
        </div>
        
        <h2 style={styles.screenTitle}>Initializing AI Model</h2>
        
        <div style={styles.loadingSteps}>
          <div style={styles.stepItem}>
            <span style={styles.stepDot}>●</span>
            <span>Loading neural network weights...</span>
          </div>
          <div style={styles.stepItem}>
            <span style={styles.stepDot}>●</span>
            <span>Initializing camera stream...</span>
          </div>
          <div style={styles.stepItem}>
            <span style={styles.stepDot}>●</span>
            <span>Setting up gesture detection...</span>
          </div>
        </div>
        
        <p style={styles.screenDescription}>
          This may take a few seconds on first load.
        </p>
      </div>
      
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

/**
 * ListeningScreen
 * Main camera feed view with scanning animation overlay
 */
const ListeningScreen: React.FC = () => {
  return (
    <div className="screen listening-screen" style={styles.screenContainer}>
      <div style={styles.cameraFeedContainer}>
        {/* Camera feed placeholder */}
        <div style={styles.cameraPlaceholder}>
          <div style={styles.cameraFrame}>
            <div style={styles.scanningLine}></div>
            <div style={{ ...styles.cornerMarker, top: 0, left: 0 }}>┌</div>
            <div style={{ ...styles.cornerMarker, top: 0, right: 0 }}>┐</div>
            <div style={{ ...styles.cornerMarker, bottom: 0, left: 0 }}>└</div>
            <div style={{ ...styles.cornerMarker, bottom: 0, right: 0 }}>┘</div>
          </div>
        </div>
        
        {/* Status overlay */}
        <div style={styles.statusOverlay}>
          <div style={styles.pulsingDot}></div>
          <p style={styles.listeningText}>Listening...</p>
          <p style={styles.instructionText}>Show a sign gesture to the camera</p>
        </div>
      </div>
      
      <style>{`
        @keyframes scan {
          0% { top: 10%; }
          50% { top: 70%; }
          100% { top: 10%; }
        }
        
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.2); opacity: 0.7; }
        }
      `}</style>
    </div>
  );
};

/**
 * SignRecognizedScreen
 * Displays the successfully recognized sign text/label
 */
interface SignRecognizedScreenProps {
  recognizedSign: string | null;
  onContinue: () => void;
}

const SignRecognizedScreen: React.FC<SignRecognizedScreenProps> = ({ 
  recognizedSign, 
  onContinue 
}) => {
  return (
    <div className="screen sign-recognized-screen" style={styles.screenContainer}>
      <div style={styles.contentContainer}>
        <div style={styles.successIconContainer}>
          <span style={styles.successIcon}>✓</span>
        </div>
        
        <h2 style={styles.screenTitle}>Sign Recognized!</h2>
        
        <div style={styles.recognizedSignBox}>
          <p style={styles.recognizedSignLabel}>Detected Sign</p>
          <p style={styles.recognizedSignText}>
            {recognizedSign || 'Unknown Sign'}
          </p>
          <p style={styles.confidenceText}>Confidence: 94%</p>
        </div>
        
        <div style={styles.buttonGroup}>
          <button 
            onClick={onContinue}
            style={styles.primaryButton}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#0056b3';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#007bff';
            }}
          >
            Speak This Word
          </button>
          
          <button 
            onClick={onContinue}
            style={styles.secondaryButton}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#f0f0f0';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#ffffff';
            }}
          >
            Continue Listening
          </button>
        </div>
      </div>
    </div>
  );
};

/**
 * SpeakingScreen
 * Displays text-to-speech audio wave animation
 */
interface SpeakingScreenProps {
  text: string | null;
  onComplete: () => void;
}

const SpeakingScreen: React.FC<SpeakingScreenProps> = ({ 
  text, 
  onComplete 
}) => {
  // Generate animated audio waveform bars
  const waveformBars = Array.from({ length: 12 }, (_, i) => i);
  
  return (
    <div className="screen speaking-screen" style={styles.screenContainer}>
      <div style={styles.contentContainer}>
        <h2 style={styles.screenTitle}>Speaking</h2>
        
        <div style={styles.audioWaveContainer}>
          <p style={styles.speakingText}>{text || 'Unknown'}</p>
          
          <div style={styles.waveformContainer}>
            {waveformBars.map((bar) => (
              <div
                key={bar}
                style={{
                  ...styles.waveformBar,
                  animation: `wave 0.6s ease-in-out ${bar * 0.05}s infinite`,
                }}
              />
            ))}
          </div>
          
          <div style={styles.audioProgress}>
            <div style={styles.audioProgressBar}></div>
          </div>
          
          <p style={styles.smallText}>Audio playing...</p>
        </div>
        
        <button 
          onClick={onComplete}
          style={styles.secondaryButton}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = '#f0f0f0';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = '#ffffff';
          }}
        >
          Continue Listening
        </button>
      </div>
      
      <style>{`
        @keyframes wave {
          0%, 100% { height: 8px; }
          50% { height: 40px; }
        }
      `}</style>
    </div>
  );
};

/**
 * ErrorScreen
 * Displays error message with retry option
 */
interface ErrorScreenProps {
  errorMessage: string | null;
  onRetry: () => void;
}

const ErrorScreen: React.FC<ErrorScreenProps> = ({ 
  errorMessage, 
  onRetry 
}) => {
  return (
    <div className="screen error-screen" style={styles.screenContainer}>
      <div style={styles.contentContainer}>
        <div style={styles.errorIconContainer}>
          <span style={styles.errorIcon}>⚠</span>
        </div>
        
        <h2 style={styles.screenTitle}>Something Went Wrong</h2>
        
        <div style={styles.errorBox}>
          <p style={styles.errorBoxTitle}>Error Details</p>
          <p style={styles.errorMessage}>
            {errorMessage || 'An unexpected error occurred. Please try again.'}
          </p>
        </div>
        
        <div style={styles.troubleshootingList}>
          <p style={styles.troubleshootingTitle}>Troubleshooting:</p>
          <ul style={styles.troubleshootingItems}>
            <li>Check that your camera is connected and enabled</li>
            <li>Ensure browser permissions are granted</li>
            <li>Try refreshing the page</li>
            <li>Check your internet connection</li>
          </ul>
        </div>
        
        <div style={styles.buttonGroup}>
          <button 
            onClick={onRetry}
            style={styles.primaryButton}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#0056b3';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#007bff';
            }}
          >
            Retry
          </button>
          
          <button 
            onClick={() => window.location.reload()}
            style={styles.secondaryButton}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#f0f0f0';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#ffffff';
            }}
          >
            Reload Page
          </button>
        </div>
      </div>
    </div>
  );
};

/**
 * ============================================================================
 * DEV CONTROL PANEL - For testing state transitions
 * ============================================================================
 */

interface DevControlPanelProps {
  currentState: AppState;
  onStateChange: (transition: StateTransition) => void;
}

const DevControlPanel: React.FC<DevControlPanelProps> = ({ 
  currentState, 
  onStateChange 
}) => {
  const handleStateClick = (newState: AppState, data?: StateTransition['data']) => {
    onStateChange({ state: newState, data });
  };

  return (
    <div style={styles.devPanel}>
      <div style={styles.devPanelHeader}>
        <span style={styles.devPanelTitle}>🔧 DEV CONTROL PANEL</span>
        <span style={styles.currentStateLabel}>
          Current State: <strong>{currentState}</strong>
        </span>
      </div>
      
      <div style={styles.devButtonsContainer}>
        <button
          onClick={() => handleStateClick('permission_needed')}
          style={{
            ...styles.devButton,
            ...(currentState === 'permission_needed' ? styles.devButtonActive : {}),
          }}
        >
          Permission Needed
        </button>
        
        <button
          onClick={() => handleStateClick('loading_model')}
          style={{
            ...styles.devButton,
            ...(currentState === 'loading_model' ? styles.devButtonActive : {}),
          }}
        >
          Loading Model
        </button>
        
        <button
          onClick={() => handleStateClick('listening')}
          style={{
            ...styles.devButton,
            ...(currentState === 'listening' ? styles.devButtonActive : {}),
          }}
        >
          Listening
        </button>
        
        <button
          onClick={() => handleStateClick('sign_recognized', {
            recognizedSign: 'HELLO',
          })}
          style={{
            ...styles.devButton,
            ...(currentState === 'sign_recognized' ? styles.devButtonActive : {}),
          }}
        >
          Sign Recognized
        </button>
        
        <button
          onClick={() => handleStateClick('speaking', {
            recognizedSign: 'HELLO',
          })}
          style={{
            ...styles.devButton,
            ...(currentState === 'speaking' ? styles.devButtonActive : {}),
          }}
        >
          Speaking
        </button>
        
        <button
          onClick={() => handleStateClick('error', {
            errorMessage: 'Camera access denied or model failed to load',
          })}
          style={{
            ...styles.devButton,
            ...(currentState === 'error' ? styles.devButtonActive : {}),
          }}
        >
          Error
        </button>
      </div>
    </div>
  );
};

/**
 * ============================================================================
 * MAIN APPLICATION COMPONENT - State Machine Router
 * ============================================================================
 */

/**
 * SignLanguageApp
 * Main component that manages the state machine and renders appropriate screen
 */
export const SignLanguageApp: React.FC = () => {
  // State management
  const [currentState, setCurrentState] = useState<AppState>('permission_needed');
  const [contextData, setContextData] = useState<AppContextData>({
    recognizedSign: null,
    errorMessage: null,
    audioWaveform: [],
  });

  /**
   * Handle state transitions with optional data payload
   */
  const handleStateTransition = useCallback((transition: StateTransition) => {
    setCurrentState(transition.state);
    
    if (transition.data) {
      setContextData(prev => ({
        ...prev,
        recognizedSign: transition.data?.recognizedSign ?? prev.recognizedSign,
        errorMessage: transition.data?.errorMessage ?? prev.errorMessage,
        audioWaveform: transition.data?.audioWaveform ?? prev.audioWaveform,
      }));
    }
  }, []);

  /**
   * State-specific action handlers
   */
  const handleGrantPermission = () => {
    handleStateTransition({ state: 'loading_model' });
  };

  const handleStartSpeaking = () => {
    handleStateTransition({ 
      state: 'speaking',
      data: { recognizedSign: contextData.recognizedSign ?? undefined }
    });
  };

  const handleSpeakingComplete = () => {
    handleStateTransition({ state: 'listening' });
  };

  const handleRetry = () => {
    handleStateTransition({ state: 'listening' });
  };

  /**
   * Render current screen based on app state
   */
  const renderCurrentScreen = () => {
    switch (currentState) {
      case 'permission_needed':
        return (
          <PermissionNeededScreen onGrantPermission={handleGrantPermission} />
        );
      
      case 'loading_model':
        return <LoadingModelScreen />;
      
      case 'listening':
        return <ListeningScreen />;
      
      case 'sign_recognized':
        return (
          <SignRecognizedScreen
            recognizedSign={contextData.recognizedSign}
            onContinue={handleStartSpeaking}
          />
        );
      
      case 'speaking':
        return (
          <SpeakingScreen
            text={contextData.recognizedSign}
            onComplete={handleSpeakingComplete}
          />
        );
      
      case 'error':
        return (
          <ErrorScreen
            errorMessage={contextData.errorMessage}
            onRetry={handleRetry}
          />
        );
      
      default:
        const _exhaustiveCheck: never = currentState;
        return _exhaustiveCheck;
    }
  };

  return (
    <div style={styles.appContainer}>
      {/* Main content area */}
      <div style={styles.mainContent}>
        {renderCurrentScreen()}
      </div>

      {/* Dev control panel - fixed at bottom */}
      <DevControlPanel 
        currentState={currentState}
        onStateChange={handleStateTransition}
      />
    </div>
  );
};

/**
 * ============================================================================
 * STYLES - Comprehensive styling for all components
 * ============================================================================
 */

const styles: { [key: string]: React.CSSProperties } = {
  // App container
  appContainer: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    width: '100%',
    backgroundColor: '#f5f5f5',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", sans-serif',
  },

  mainContent: {
    flex: 1,
    display: 'flex',
    overflow: 'hidden',
  },

  // Screen container
  screenContainer: {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '20px',
    backgroundColor: '#ffffff',
  },

  contentContainer: {
    maxWidth: '600px',
    width: '100%',
    textAlign: 'center',
  },

  // Typography
  screenTitle: {
    fontSize: '28px',
    fontWeight: 600,
    color: '#1a1a1a',
    marginBottom: '16px',
    marginTop: '16px',
  },

  screenDescription: {
    fontSize: '16px',
    color: '#666',
    lineHeight: '1.6',
    marginBottom: '24px',
  },

  smallText: {
    fontSize: '12px',
    color: '#999',
    marginTop: '16px',
  },

  // Icons and visual elements
  iconContainer: {
    marginBottom: '24px',
  },

  largeIcon: {
    fontSize: '64px',
    display: 'inline-block',
  },

  successIconContainer: {
    marginBottom: '24px',
  },

  successIcon: {
    fontSize: '64px',
    color: '#28a745',
    backgroundColor: '#d4edda',
    borderRadius: '50%',
    padding: '20px',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '100px',
    height: '100px',
  },

  errorIconContainer: {
    marginBottom: '24px',
  },

  errorIcon: {
    fontSize: '64px',
    color: '#dc3545',
    backgroundColor: '#f8d7da',
    borderRadius: '50%',
    padding: '20px',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '100px',
    height: '100px',
  },

  // Feature list
  featureList: {
    marginBottom: '32px',
    textAlign: 'left',
    display: 'inline-block',
  },

  featureItem: {
    fontSize: '14px',
    color: '#333',
    marginBottom: '12px',
    display: 'flex',
    alignItems: 'center',
  },

  checkmark: {
    color: '#28a745',
    marginRight: '12px',
    fontSize: '18px',
  },

  // Loading
  spinnerContainer: {
    marginBottom: '24px',
    display: 'flex',
    justifyContent: 'center',
  },

  spinner: {
    width: '60px',
    height: '60px',
    border: '4px solid #f0f0f0',
    borderTop: '4px solid #007bff',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
  },

  loadingSteps: {
    marginBottom: '24px',
    textAlign: 'left',
    display: 'inline-block',
  },

  stepItem: {
    fontSize: '14px',
    color: '#666',
    marginBottom: '8px',
    display: 'flex',
    alignItems: 'center',
  },

  stepDot: {
    color: '#007bff',
    marginRight: '10px',
    fontSize: '10px',
  },

  // Camera feed
  cameraFeedContainer: {
    position: 'relative',
    width: '100%',
    maxWidth: '500px',
    margin: '0 auto',
  },

  cameraPlaceholder: {
    backgroundColor: '#000',
    borderRadius: '12px',
    overflow: 'hidden',
    aspectRatio: '4 / 3',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },

  cameraFrame: {
    position: 'relative',
    width: '100%',
    height: '100%',
  },

  scanningLine: {
    position: 'absolute',
    width: '100%',
    height: '2px',
    backgroundColor: '#00ff00',
    boxShadow: '0 0 10px rgba(0, 255, 0, 0.5)',
    animation: 'scan 2s ease-in-out infinite',
    top: '10%',
  },

  cornerMarker: {
    position: 'absolute',
    color: '#00ff00',
    fontSize: '24px',
    fontWeight: 'bold',
  },

  statusOverlay: {
    position: 'absolute',
    bottom: '20px',
    left: '50%',
    transform: 'translateX(-50%)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    color: 'white',
    zIndex: 10,
  },

  pulsingDot: {
    width: '12px',
    height: '12px',
    backgroundColor: '#00ff00',
    borderRadius: '50%',
    marginBottom: '8px',
    boxShadow: '0 0 10px rgba(0, 255, 0, 0.8)',
    animation: 'pulse 1s ease-in-out infinite',
  },

  listeningText: {
    fontSize: '16px',
    fontWeight: 600,
    margin: '0 0 4px 0',
  },

  instructionText: {
    fontSize: '12px',
    color: '#ccc',
    margin: 0,
  },

  // Sign recognized
  recognizedSignBox: {
    backgroundColor: '#f0f8ff',
    border: '2px solid #007bff',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '32px',
  },

  recognizedSignLabel: {
    fontSize: '12px',
    color: '#666',
    margin: '0 0 8px 0',
    textTransform: 'uppercase',
    letterSpacing: '1px',
  },

  recognizedSignText: {
    fontSize: '48px',
    fontWeight: 700,
    color: '#007bff',
    margin: '8px 0',
    letterSpacing: '2px',
  },

  confidenceText: {
    fontSize: '12px',
    color: '#999',
    margin: '8px 0 0 0',
  },

  // Speaking
  audioWaveContainer: {
    marginBottom: '32px',
  },

  speakingText: {
    fontSize: '36px',
    fontWeight: 700,
    color: '#007bff',
    margin: '0 0 24px 0',
    letterSpacing: '2px',
  },

  waveformContainer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '4px',
    height: '60px',
    marginBottom: '16px',
  },

  waveformBar: {
    width: '4px',
    height: '8px',
    backgroundColor: '#007bff',
    borderRadius: '2px',
  },

  audioProgress: {
    width: '100%',
    height: '4px',
    backgroundColor: '#f0f0f0',
    borderRadius: '2px',
    overflow: 'hidden',
    marginBottom: '12px',
  },

  audioProgressBar: {
    height: '100%',
    backgroundColor: '#007bff',
    width: '35%',
    animation: 'progress 3s ease-in-out',
  },

  // Error
  errorBox: {
    backgroundColor: '#fff5f5',
    border: '1px solid #dc3545',
    borderRadius: '8px',
    padding: '16px',
    marginBottom: '24px',
    textAlign: 'left',
  },

  errorBoxTitle: {
    fontSize: '12px',
    fontWeight: 600,
    color: '#dc3545',
    margin: '0 0 8px 0',
    textTransform: 'uppercase',
  },

  errorMessage: {
    fontSize: '14px',
    color: '#666',
    margin: 0,
    lineHeight: '1.5',
  },

  troubleshootingList: {
    textAlign: 'left',
    marginBottom: '24px',
  },

  troubleshootingTitle: {
    fontSize: '12px',
    fontWeight: 600,
    color: '#1a1a1a',
    margin: '0 0 12px 0',
    textTransform: 'uppercase',
  },

  troubleshootingItems: {
    margin: 0,
    paddingLeft: '20px',
  },

  // Buttons
  primaryButton: {
    backgroundColor: '#007bff',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    padding: '12px 24px',
    fontSize: '16px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background-color 0.2s',
    marginRight: '8px',
    marginTop: '8px',
  },

  secondaryButton: {
    backgroundColor: '#ffffff',
    color: '#007bff',
    border: '2px solid #007bff',
    borderRadius: '8px',
    padding: '10px 22px',
    fontSize: '16px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background-color 0.2s',
    marginRight: '8px',
    marginTop: '8px',
  },

  buttonGroup: {
    display: 'flex',
    justifyContent: 'center',
    flexWrap: 'wrap',
    gap: '8px',
    marginTop: '16px',
  },

  // Dev panel
  devPanel: {
    backgroundColor: '#2c3e50',
    color: '#ecf0f1',
    padding: '16px',
    borderTop: '2px solid #34495e',
    minHeight: '80px',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
  },

  devPanelHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '12px',
  },

  devPanelTitle: {
    fontSize: '12px',
    fontWeight: 700,
    letterSpacing: '1px',
    color: '#f39c12',
  },

  currentStateLabel: {
    fontSize: '12px',
    color: '#bdc3c7',
  },

  devButtonsContainer: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
  },

  devButton: {
    backgroundColor: '#34495e',
    color: '#ecf0f1',
    border: '1px solid #7f8c8d',
    borderRadius: '4px',
    padding: '8px 12px',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s',
    whiteSpace: 'nowrap',
  },

  devButtonActive: {
    backgroundColor: '#f39c12',
    color: '#2c3e50',
    border: '1px solid #f39c12',
    boxShadow: '0 0 8px rgba(243, 156, 18, 0.5)',
  },
};

export default SignLanguageApp;
