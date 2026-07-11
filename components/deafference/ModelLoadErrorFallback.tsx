'use client';

import styles from './ErrorScreens.module.css';

interface ModelLoadErrorFallbackProps {
  errorMessage: string;
  onRetry: () => void;
  onContinueMockMode: () => void;
}

export default function ModelLoadErrorFallback({
  errorMessage,
  onRetry,
  onContinueMockMode,
}: ModelLoadErrorFallbackProps) {
  return (
    <div className={styles.errorScreenContainer}>
      <div className={styles.errorScreen} role="alert" aria-live="assertive">
        <div className={styles.errorIcon} aria-hidden="true">
          ⚠️
        </div>

        <h1 className={styles.errorTitle}>AI Model Failed to Load</h1>

        <p className={styles.errorDescription}>
          The sign recognition model could not be initialized. This is usually caused by a
          network error or connection timeout.
        </p>

        <div className={styles.recommendationBox}>
          <strong>Error details:</strong>
          <p>{errorMessage}</p>
        </div>

        <div className={styles.actionButtons}>
          <button
            type="button"
            className={`${styles.button} ${styles.primaryButton}`}
            onClick={onRetry}
          >
            Retry Connection
          </button>
          <button
            type="button"
            className={`${styles.button} ${styles.secondaryButton}`}
            onClick={onContinueMockMode}
          >
            Continue in Mock Mode
          </button>
        </div>
      </div>
    </div>
  );
}
