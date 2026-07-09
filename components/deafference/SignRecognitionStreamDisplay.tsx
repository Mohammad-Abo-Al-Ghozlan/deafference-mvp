/**
 * Example Component: Sign Recognition Stream Display
 * Demonstrates useGlossBuffer + useMockEventGenerator integration
 * Shows gloss buffer state, live sentence assembly, and controls
 */

'use client';

import React, { useState } from 'react';
import { useSignRecognitionPipeline } from '@/hooks/useSignRecognitionPipeline';

interface StreamDisplayProps {
  /** Custom className for root container */
  className?: string;
  /** Show debug info */
  showDebug?: boolean;
}

/**
 * Sign Recognition Stream Display Component
 *
 * Features:
 * - Real-time gloss buffer visualization
 * - Live sentence assembly
 * - Mock event simulation controls
 * - Debug information (confidence, buffer size, etc.)
 * - Clear/Reset controls
 *
 * @example
 * <SignRecognitionStreamDisplay showDebug />
 */
export const SignRecognitionStreamDisplay: React.FC<StreamDisplayProps> = ({
  className = '',
  showDebug = false,
}) => {
  const {
    glossBufferState,
    getSentenceString,
    clearBuffer,
    resetSentence,
    isSimulating,
    toggleSimulation,
    eventCount,
    updateBufferConfig,
  } = useSignRecognitionPipeline();

  const [debounceMs, setDebounceMs] = useState(1200);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.7);

  const handleDebounceTuning = (ms: number) => {
    setDebounceMs(ms);
    updateBufferConfig({ debounceTimeoutMs: ms });
  };

  const handleConfidenceTuning = (threshold: number) => {
    setConfidenceThreshold(threshold);
    updateBufferConfig({ confidenceThreshold: threshold });
  };

  return (
    <div className={`sign-recognition-stream-display ${className}`}>
      {/* Header */}
      <div className="stream-header">
        <h2>Sign Language Recognition Stream</h2>
        <div className="status-badge">
          {isSimulating ? (
            <span className="status-active">🔴 Live</span>
          ) : (
            <span className="status-idle">⚪ Idle</span>
          )}
        </div>
      </div>

      {/* Current Buffer Visualization */}
      <div className="buffer-section">
        <h3>Gloss Buffer (Current Tokens)</h3>
        <div className="buffer-container">
          {glossBufferState.glossBuffer.length === 0 ? (
            <div className="buffer-empty">Waiting for signs...</div>
          ) : (
            <div className="buffer-tokens">
              {glossBufferState.glossBuffer.map((token, idx) => (
                <div key={idx} className="buffer-token">
                  <span className="token-label">{token.label}</span>
                  <span className="token-confidence">
                    {(token.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          )}
          <div className="buffer-stats">
            <span className="stat">
              Buffer Size: <strong>{glossBufferState.glossBuffer.length}</strong>
            </span>
            <span className="stat">
              Avg Confidence:{' '}
              <strong>{(glossBufferState.averageConfidence * 100).toFixed(1)}%</strong>
            </span>
            <span className="stat">
              Status: <strong>{glossBufferState.bufferStatus}</strong>
            </span>
          </div>
        </div>
      </div>

      {/* Stabilized Sentence */}
      <div className="sentence-section">
        <h3>Stabilized Sentence</h3>
        <div className="sentence-container">
          <div className="sentence-text">
            {getSentenceString() || '(No words finalized yet)'}
          </div>
          <div className="sentence-stats">
            <span className="stat">
              Words: <strong>{glossBufferState.stabilizedSentence.length}</strong>
            </span>
            <span className="stat">
              Total Processed:{' '}
              <strong>{glossBufferState.totalSignsProcessed}</strong>
            </span>
            <span className="stat">
              Finalized:{' '}
              <strong>{glossBufferState.totalWordsFinalized}</strong>
            </span>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="controls-section">
        <h3>Controls</h3>

        {/* Simulation Controls */}
        <div className="control-group">
          <label>Simulation</label>
          <div className="button-group">
            <button
              className={`btn ${isSimulating ? 'btn-primary' : 'btn-secondary'}`}
              onClick={toggleSimulation}
            >
              {isSimulating ? '⏸ Stop Simulation' : '▶ Start Simulation'}
            </button>
            <span className="event-count">Events: {eventCount}</span>
          </div>
        </div>

        {/* Buffer Actions */}
        <div className="control-group">
          <label>Buffer Actions</label>
          <div className="button-group">
            <button className="btn btn-warning" onClick={clearBuffer}>
              🗑 Clear Buffer
            </button>
            <button className="btn btn-danger" onClick={resetSentence}>
              🔄 Reset Sentence
            </button>
          </div>
        </div>

        {/* Debounce Tuning */}
        <div className="control-group">
          <label>Debounce Timeout: {debounceMs}ms</label>
          <input
            type="range"
            min="500"
            max="3000"
            step="100"
            value={debounceMs}
            onChange={(e) => handleDebounceTuning(parseInt(e.target.value))}
            className="slider"
          />
          <small>Time before finalizing buffer (ms)</small>
        </div>

        {/* Confidence Threshold Tuning */}
        <div className="control-group">
          <label>Confidence Threshold: {(confidenceThreshold * 100).toFixed(0)}%</label>
          <input
            type="range"
            min="0.5"
            max="0.99"
            step="0.05"
            value={confidenceThreshold}
            onChange={(e) => handleConfidenceTuning(parseFloat(e.target.value))}
            className="slider"
          />
          <small>Minimum confidence to accept a sign</small>
        </div>
      </div>

      {/* Debug Panel */}
      {showDebug && (
        <div className="debug-section">
          <h3>🐛 Debug Information</h3>
          <pre className="debug-content">
            {JSON.stringify(
              {
                bufferState: glossBufferState,
                sentence: getSentenceString(),
              },
              null,
              2
            )}
          </pre>
        </div>
      )}

      {/* Inline Styles */}
      <style jsx>{`
        .sign-recognition-stream-display {
          padding: 1.5rem;
          background: linear-gradient(135deg, #1e1e2e 0%, #2a2a3e 100%);
          border-radius: 12px;
          color: #e0e0e0;
          font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }

        .stream-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 1.5rem;
          border-bottom: 2px solid #3a3a4a;
          padding-bottom: 1rem;
        }

        .stream-header h2 {
          margin: 0;
          font-size: 1.5rem;
          font-weight: 600;
        }

        .status-badge {
          font-size: 1rem;
          font-weight: 500;
        }

        .status-active {
          color: #ff4444;
          animation: pulse 1s infinite;
        }

        .status-idle {
          color: #888;
        }

        @keyframes pulse {
          0%, 100% {
            opacity: 1;
          }
          50% {
            opacity: 0.5;
          }
        }

        .buffer-section,
        .sentence-section,
        .controls-section,
        .debug-section {
          margin-bottom: 1.5rem;
        }

        h3 {
          font-size: 1.1rem;
          margin: 0 0 0.8rem 0;
          font-weight: 600;
          color: #e8e8e8;
        }

        .buffer-container,
        .sentence-container {
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid #3a3a4a;
          border-radius: 8px;
          padding: 1rem;
        }

        .buffer-empty {
          text-align: center;
          padding: 2rem 1rem;
          color: #888;
          font-style: italic;
        }

        .buffer-tokens {
          display: flex;
          flex-wrap: wrap;
          gap: 0.5rem;
          margin-bottom: 1rem;
        }

        .buffer-token {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          background: linear-gradient(135deg, #4a5f8f 0%, #2a4a6f 100%);
          padding: 0.5rem 1rem;
          border-radius: 6px;
          border: 1px solid #5a7faf;
          box-shadow: 0 2px 8px rgba(74, 95, 143, 0.3);
        }

        .token-label {
          font-weight: 600;
          color: #fff;
        }

        .token-confidence {
          font-size: 0.85rem;
          color: #b0b0ff;
          background: rgba(0, 0, 0, 0.2);
          padding: 0.2rem 0.5rem;
          border-radius: 3px;
        }

        .buffer-stats,
        .sentence-stats {
          display: flex;
          gap: 1rem;
          font-size: 0.9rem;
          padding-top: 0.5rem;
          border-top: 1px solid rgba(255, 255, 255, 0.1);
        }

        .stat {
          color: #b0b0b0;
        }

        .stat strong {
          color: #ff8844;
          font-weight: 600;
        }

        .sentence-text {
          font-size: 1.2rem;
          font-weight: 500;
          padding: 1rem;
          background: rgba(0, 0, 0, 0.2);
          border-radius: 6px;
          border-left: 4px solid #ff8844;
          margin-bottom: 0.8rem;
          min-height: 3rem;
          display: flex;
          align-items: center;
        }

        .control-group {
          background: rgba(0, 0, 0, 0.2);
          border: 1px solid #3a3a4a;
          border-radius: 6px;
          padding: 1rem;
          margin-bottom: 0.8rem;
        }

        .control-group > label {
          display: block;
          font-weight: 600;
          margin-bottom: 0.5rem;
          font-size: 0.95rem;
        }

        .button-group {
          display: flex;
          gap: 0.5rem;
          flex-wrap: wrap;
          align-items: center;
        }

        .btn {
          padding: 0.6rem 1.2rem;
          border: 1px solid #3a3a4a;
          border-radius: 6px;
          cursor: pointer;
          font-weight: 500;
          transition: all 0.2s;
          font-size: 0.9rem;
        }

        .btn-primary {
          background: #4a8fff;
          color: white;
          border-color: #5a9fff;
        }

        .btn-primary:hover {
          background: #3a7fff;
          box-shadow: 0 2px 8px rgba(74, 143, 255, 0.3);
        }

        .btn-secondary {
          background: #3a3a4a;
          color: #b0b0b0;
          border-color: #4a4a5a;
        }

        .btn-secondary:hover {
          background: #4a4a5a;
        }

        .btn-warning {
          background: #ff8844;
          color: white;
          border-color: #ffaa66;
        }

        .btn-warning:hover {
          background: #ff7733;
        }

        .btn-danger {
          background: #ff4444;
          color: white;
          border-color: #ff6666;
        }

        .btn-danger:hover {
          background: #ff3333;
        }

        .event-count {
          color: #888;
          font-size: 0.85rem;
        }

        .slider {
          width: 100%;
          height: 6px;
          border-radius: 3px;
          background: linear-gradient(90deg, #3a3a4a 0%, #4a6a8a 100%);
          outline: none;
          margin: 0.5rem 0;
          cursor: pointer;
        }

        small {
          display: block;
          margin-top: 0.3rem;
          color: #888;
          font-size: 0.8rem;
        }

        .debug-section {
          background: rgba(0, 0, 0, 0.5);
          border: 1px solid #4a4a6a;
          border-radius: 6px;
          padding: 1rem;
        }

        .debug-content {
          background: rgba(0, 0, 0, 0.3);
          border: 1px solid #2a2a3a;
          border-radius: 4px;
          padding: 1rem;
          overflow-x: auto;
          font-size: 0.8rem;
          line-height: 1.4;
          color: #8f8;
          margin: 0;
        }

        @media (max-width: 768px) {
          .stream-header {
            flex-direction: column;
            gap: 0.5rem;
            align-items: flex-start;
          }

          .buffer-tokens {
            flex-direction: column;
          }

          .buffer-token {
            width: 100%;
          }

          .button-group {
            flex-direction: column;
          }

          .btn {
            width: 100%;
          }
        }
      `}</style>
    </div>
  );
};

export default SignRecognitionStreamDisplay;
