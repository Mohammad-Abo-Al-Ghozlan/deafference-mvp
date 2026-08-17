/**
 * Complete Working Example: Translation App Integration
 * Drop this into your translation app to enable the gloss buffer
 */

'use client';

import React from 'react';
import { SignRecognitionStreamDisplay } from '@/components/deafference/SignRecognitionStreamDisplay';

/**
 * Translation App Page with Gloss Buffer Integration
 * This example shows how to integrate the stabilization layer
 * into your existing translation/listening workspace
 */
export default function TranslationAppWithBuffer() {
  return (
    <div className="translation-app-container">
      {/* Header */}
      <header className="app-header">
        <h1>🎯 Deafference Sign Language Translator</h1>
        <p className="subtitle">AI-powered sign language recognition with real-time stabilization</p>
      </header>

      {/* Main Content */}
      <main className="app-main">
        {/* Gloss Buffer Stream Display */}
        <section className="stream-section">
          <SignRecognitionStreamDisplay showDebug={true} />
        </section>

        {/* Additional Info */}
        <section className="info-section">
          <div className="info-card">
            <h3>📊 How It Works</h3>
            <ol>
              <li>
                <strong>Start Simulation:</strong> Click "Start Simulation" to begin receiving mock sign
                predictions
              </li>
              <li>
                <strong>Token Buffering:</strong> Each recognized sign is added to the gloss buffer
              </li>
              <li>
                <strong>Debounce & Wait:</strong> System waits 1200ms for more signs
              </li>
              <li>
                <strong>Finalize Word:</strong> When silence is detected, buffer converts to a single word
                using majority voting
              </li>
              <li>
                <strong>Build Sentence:</strong> Finalized words are appended to the stabilized sentence
              </li>
            </ol>
          </div>

          <div className="info-card">
            <h3>⚙️ Configuration Options</h3>
            <dl>
              <dt>Debounce Timeout</dt>
              <dd>Time (ms) to wait before finalizing buffer as complete word. Lower = faster but more false positives.</dd>

              <dt>Confidence Threshold</dt>
              <dd>Minimum confidence (0-100%) to accept a recognized sign. Higher = fewer errors but might miss signs.</dd>

              <dt>Max Buffer Size</dt>
              <dd>Maximum number of tokens before auto-finalizing. Prevents accumulation during continuous motion.</dd>
            </dl>
          </div>

          <div className="info-card">
            <h3>🎮 Usage Tips</h3>
            <ul>
              <li>
                <strong>Fast signing:</strong> Reduce debounce timeout to 800-1000ms and confidence threshold to 0.65
              </li>
              <li>
                <strong>Careful articulation:</strong> Increase debounce timeout to 1500ms for precise recognition
              </li>
              <li>
                <strong>Noisy environment:</strong> Increase confidence threshold to 0.80-0.85
              </li>
              <li>
                <strong>Getting false positives:</strong> Click "Clear Buffer" to skip current predictions
              </li>
              <li>
                <strong>Starting over:</strong> Click "Reset Sentence" to clear all finalized words
              </li>
            </ul>
          </div>
        </section>

        {/* Code Example */}
        <section className="code-section">
          <h3>💻 Integration Code Example</h3>
          <pre className="code-block">
{`// In your page or component:
import { useSignRecognitionPipeline } from '@/hooks/useSignRecognitionPipeline';

export default function YourComponent() {
  const {
    glossBufferState,
    getSentenceString,
    clearBuffer,
    resetSentence,
    isSimulating,
    toggleSimulation,
  } = useSignRecognitionPipeline();

  return (
    <div>
      {/* Display current sentence */}
      <div className="output">
        <h2>Translation Output</h2>
        <p className="sentence">
          {getSentenceString() || '(Listening...)'}
        </p>
      </div>

      {/* Display buffer status */}
      <div className="status">
        <p>Status: {glossBufferState.bufferStatus}</p>
        <p>Buffer Size: {glossBufferState.glossBuffer.length}</p>
        <p>Words Finalized: {glossBufferState.totalWordsFinalized}</p>
      </div>

      {/* Controls */}
      <div className="controls">
        <button onClick={toggleSimulation}>
          {isSimulating ? 'Stop' : 'Start'} Recognition
        </button>
        <button onClick={clearBuffer}>Clear Buffer</button>
        <button onClick={resetSentence}>Reset Sentence</button>
      </div>
    </div>
  );
}`}
          </pre>
        </section>
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <p>
          Gloss Buffer & Stabilization System · Built for Deafference ·{' '}
          <a href="/docs/GLOSS_BUFFER_GUIDE.md" target="_blank" rel="noopener noreferrer">
            Full Documentation
          </a>
        </p>
      </footer>

      {/* Styles */}
      <style jsx>{`
        .translation-app-container {
          min-height: 100vh;
          background: linear-gradient(135deg, #0f0f1e 0%, #1a1a2e 100%);
          color: #e0e0e0;
          font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }

        .app-header {
          background: linear-gradient(90deg, rgba(74, 143, 255, 0.1) 0%, rgba(255, 136, 68, 0.1) 100%);
          border-bottom: 2px solid rgba(74, 143, 255, 0.3);
          padding: 2rem 1rem;
          text-align: center;
        }

        .app-header h1 {
          margin: 0 0 0.5rem 0;
          font-size: 2rem;
          background: linear-gradient(135deg, #4a8fff, #ff8844);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }

        .subtitle {
          margin: 0;
          color: #888;
          font-size: 1rem;
        }

        .app-main {
          max-width: 1200px;
          margin: 0 auto;
          padding: 2rem 1rem;
        }

        .stream-section {
          margin-bottom: 2rem;
        }

        .info-section {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
          gap: 1.5rem;
          margin-bottom: 2rem;
        }

        .info-card {
          background: rgba(30, 30, 46, 0.8);
          border: 1px solid rgba(74, 143, 255, 0.2);
          border-radius: 8px;
          padding: 1.5rem;
          backdrop-filter: blur(10px);
        }

        .info-card h3 {
          margin-top: 0;
          margin-bottom: 1rem;
          color: #4a8fff;
          font-size: 1.1rem;
        }

        .info-card ol,
        .info-card ul {
          margin: 0;
          padding-left: 1.5rem;
        }

        .info-card li {
          margin-bottom: 0.5rem;
          line-height: 1.6;
        }

        .info-card dl {
          margin: 0;
        }

        .info-card dt {
          font-weight: 600;
          color: #ff8844;
          margin-top: 0.8rem;
        }

        .info-card dd {
          margin: 0 0 0.5rem 1rem;
          color: #aaa;
          font-size: 0.9rem;
        }

        .code-section {
          background: rgba(30, 30, 46, 0.8);
          border: 1px solid rgba(255, 136, 68, 0.2);
          border-radius: 8px;
          padding: 1.5rem;
          margin-bottom: 2rem;
        }

        .code-section h3 {
          margin-top: 0;
          color: #ff8844;
        }

        .code-block {
          background: rgba(0, 0, 0, 0.5);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 6px;
          padding: 1rem;
          overflow-x: auto;
          font-size: 0.85rem;
          line-height: 1.5;
          color: #8f8;
          margin: 0;
        }

        .app-footer {
          background: rgba(0, 0, 0, 0.3);
          border-top: 1px solid rgba(74, 143, 255, 0.2);
          padding: 2rem 1rem;
          text-align: center;
          color: #888;
          font-size: 0.9rem;
        }

        .app-footer a {
          color: #4a8fff;
          text-decoration: none;
        }

        .app-footer a:hover {
          text-decoration: underline;
        }

        @media (max-width: 768px) {
          .app-header h1 {
            font-size: 1.5rem;
          }

          .info-section {
            grid-template-columns: 1fr;
          }

          .code-block {
            font-size: 0.75rem;
          }
        }
      `}</style>
    </div>
  );
}
