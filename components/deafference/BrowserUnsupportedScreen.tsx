'use client';

import { useState } from 'react';
import { BROWSER_RECOMMENDATIONS } from '@/types/error-states';
import styles from './ErrorScreens.module.css';

interface BrowserUnsupportedScreenProps {
  unsupportedFeatures?: string[];
  onRetry?: () => void;
}

export default function BrowserUnsupportedScreen({
  unsupportedFeatures = ['WebRTC', 'MediaDevices API', 'WebGL'],
  onRetry,
}: BrowserUnsupportedScreenProps) {
  const [showDetails, setShowDetails] = useState(false);

  const checkBrowserSupport = () => {
    return {
      webrtc: !!window.RTCPeerConnection,
      mediaDevices: !!navigator.mediaDevices?.getUserMedia,
      webgl: !!document.createElement('canvas').getContext('webgl'),
    };
  };

  const support = checkBrowserSupport();

  return (
    <div className={styles.errorScreenContainer}>
      <div className={styles.errorScreen}>
        <div className={styles.errorIcon}>❌</div>

        <h1 className={styles.errorTitle}>Browser Not Supported</h1>

        <p className={styles.errorDescription}>
          Your browser lacks the required APIs for our sign language recognition system. 
          Please upgrade to a compatible browser to use this application.
        </p>

        <div className={styles.unsupportedFeatures}>
          <h3 className={styles.featuresTitle}>Missing Features:</h3>
          <div className={styles.featuresList}>
            {unsupportedFeatures.map((feature, index) => (
              <div key={index} className={styles.featureItem}>
                <span className={styles.featureIcon}>✗</span>
                <span className={styles.featureName}>{feature}</span>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.recommendationBox}>
          <strong>✓ Recommended Browsers:</strong>
          <p>
            The following browsers have full support for all required APIs:
          </p>
        </div>

        <div className={styles.browserGrid}>
          {BROWSER_RECOMMENDATIONS.map((browser) => (
            <a
              key={browser.name}
              href={browser.url}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.browserCard}
            >
              <div className={styles.browserCardEmoji}>{browser.emoji}</div>
              <div className={styles.browserCardName}>{browser.name}</div>
              <div className={styles.browserCardLink}>Download →</div>
            </a>
          ))}
        </div>

        <div className={styles.technicalDetails}>
          <button
            className={styles.detailsToggle}
            onClick={() => setShowDetails(!showDetails)}
          >
            {showDetails ? '▼' : '▶'} Technical Details
          </button>

          {showDetails && (
            <div className={styles.detailsContent}>
              <div className={styles.detailItem}>
                <span className={styles.detailLabel}>WebRTC Support:</span>
                <span className={support.webrtc ? styles.supported : styles.unsupported}>
                  {support.webrtc ? '✓ Supported' : '✗ Not Supported'}
                </span>
              </div>
              <div className={styles.detailItem}>
                <span className={styles.detailLabel}>MediaDevices API:</span>
                <span className={support.mediaDevices ? styles.supported : styles.unsupported}>
                  {support.mediaDevices ? '✓ Supported' : '✗ Not Supported'}
                </span>
              </div>
              <div className={styles.detailItem}>
                <span className={styles.detailLabel}>WebGL:</span>
                <span className={support.webgl ? styles.supported : styles.unsupported}>
                  {support.webgl ? '✓ Supported' : '✗ Not Supported'}
                </span>
              </div>
            </div>
          )}
        </div>

        <div className={styles.actionButtons}>
          <button
            className={`${styles.button} ${styles.primaryButton}`}
            onClick={onRetry}
          >
            Retry Detection
          </button>
          <a
            href={BROWSER_RECOMMENDATIONS[0].url}
            target="_blank"
            rel="noopener noreferrer"
            className={`${styles.button} ${styles.secondaryButton}`}
          >
            Learn More
          </a>
        </div>
      </div>
    </div>
  );
}
