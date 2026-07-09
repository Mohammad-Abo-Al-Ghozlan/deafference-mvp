'use client';

import { useEffect, useState } from 'react';
import styles from './ErrorScreens.module.css';

interface NoSignsDetectedScreenProps {
  onReset: () => void;
  timeoutSeconds?: number;
  showOverlay?: boolean;
}

export default function NoSignsDetectedScreen({
  onReset,
  timeoutSeconds = 10,
  showOverlay = true,
}: NoSignsDetectedScreenProps) {
  const [remainingSeconds, setRemainingSeconds] = useState(timeoutSeconds);

  useEffect(() => {
    const interval = setInterval(() => {
      setRemainingSeconds((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  if (!showOverlay) {
    return null;
  }

  return (
    <div className={styles.overlayContainer}>
      <div className={styles.overlay} />
      <div className={styles.overlayPrompt}>
        <div className={styles.promptEmoji}>👋</div>
        <h2 className={styles.promptTitle}>No Signs Detected</h2>
        <p className={styles.promptMessage}>
          We haven't detected any sign language recently. Make sure your hands are visible 
          and well-lit for the camera to track your gestures.
        </p>
        <div className={styles.promptCounter}>
          <span className={styles.counterLabel}>Timeout in</span>
          <span className={styles.counterValue}>{remainingSeconds}s</span>
        </div>
        <button className={`${styles.button} ${styles.primaryButton}`} onClick={onReset}>
          Keep Listening
        </button>
        <div className={styles.promptTip}>
          💡 <strong>Tip:</strong> Keep your hands within the camera frame
        </div>
      </div>
    </div>
  );
}
