'use client';

import { useState } from 'react';
import { CAMERA_PERMISSION_INSTRUCTIONS } from '@/types/error-states';
import styles from './ErrorScreens.module.css';

interface CameraDeniedScreenProps {
  onRetry?: () => void;
}

type BrowserType = 'chrome' | 'firefox' | 'safari' | 'edge';

export default function CameraDeniedScreen({ onRetry }: CameraDeniedScreenProps) {
  const [expandedBrowser, setExpandedBrowser] = useState<BrowserType | null>(null);

  const browsers: BrowserType[] = ['chrome', 'firefox', 'safari', 'edge'];
  const browserEmojis: Record<BrowserType, string> = {
    chrome: '🌐',
    firefox: '🦊',
    safari: '🧭',
    edge: '⚡',
  };
  const browserNames: Record<BrowserType, string> = {
    chrome: 'Google Chrome',
    firefox: 'Mozilla Firefox',
    safari: 'Apple Safari',
    edge: 'Microsoft Edge',
  };

  return (
    <div className={styles.errorScreenContainer}>
      <div className={styles.errorScreen}>
        <div className={styles.errorIcon}>🚫</div>

        <h1 className={styles.errorTitle}>Camera Access Denied</h1>

        <p className={styles.errorDescription}>
          We need camera access to parse your ASL (American Sign Language) gestures and provide real-time sign recognition. 
          Please grant camera permission to continue using our application.
        </p>

        <div className={styles.recommendationBox}>
          <strong>📋 Why we need camera access:</strong>
          <p>
            Your camera feed allows our AI model to analyze hand gestures, movements, and positions 
            to recognize and translate sign language in real-time.
          </p>
        </div>

        <div className={styles.instructionsSection}>
          <h2 className={styles.instructionsTitle}>How to Enable Camera Access</h2>

          <div className={styles.browsersList}>
            {browsers.map((browser) => (
              <div key={browser} className={styles.browserAccordion}>
                <button
                  className={`${styles.browserButton} ${expandedBrowser === browser ? styles.expanded : ''}`}
                  onClick={() => setExpandedBrowser(expandedBrowser === browser ? null : browser)}
                >
                  <span className={styles.browserEmoji}>{browserEmojis[browser]}</span>
                  <span className={styles.browserName}>{browserNames[browser]}</span>
                  <span className={styles.accordionIcon}>
                    {expandedBrowser === browser ? '▼' : '▶'}
                  </span>
                </button>

                {expandedBrowser === browser && (
                  <div className={styles.browserSteps}>
                    {CAMERA_PERMISSION_INSTRUCTIONS[browser].steps.map((step, index) => (
                      <div key={index} className={styles.step}>
                        {step}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className={styles.actionButtons}>
          <button
            className={`${styles.button} ${styles.primaryButton}`}
            onClick={onRetry}
          >
            Grant Camera Permission
          </button>
          <button
            className={`${styles.button} ${styles.secondaryButton}`}
            onClick={() => setExpandedBrowser('chrome')}
          >
            Show Instructions
          </button>
        </div>
      </div>
    </div>
  );
}
