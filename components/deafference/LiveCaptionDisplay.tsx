// components/deafference/LiveCaptionDisplay.tsx
'use client';

import React, { useState, useEffect, useRef } from 'react';
import styles from './LiveCaptionDisplay.module.css';

const MOCK_WORDS = [
  'Hello',
  'welcome',
  'can',
  'you',
  'hear',
  'me',
  'starting',
  'live',
  'captions',
];

interface WordDisplay {
  id: string;
  text: string;
}

const LiveCaptionDisplay: React.FC = () => {
  const [words, setWords] = useState<WordDisplay[]>([]);
  const [isListening, setIsListening] = useState<boolean>(false);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const wordIndexRef = useRef<number>(0);

  useEffect(() => {
    // Start the caption streaming
    setIsListening(true);
    wordIndexRef.current = 0;

    intervalRef.current = setInterval(() => {
      if (wordIndexRef.current < MOCK_WORDS.length) {
        const newWord: WordDisplay = {
          id: `${wordIndexRef.current}-${Date.now()}`,
          text: MOCK_WORDS[wordIndexRef.current],
        };

        setWords((prevWords) => [...prevWords, newWord]);
        wordIndexRef.current += 1;
      } else {
        // Reset after all words are displayed
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
        }
        setIsListening(false);
      }
    }, 1500);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  const handleReset = (): void => {
    setWords([]);
    wordIndexRef.current = 0;
    setIsListening(true);

    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }

    intervalRef.current = setInterval(() => {
      if (wordIndexRef.current < MOCK_WORDS.length) {
        const newWord: WordDisplay = {
          id: `${wordIndexRef.current}-${Date.now()}`,
          text: MOCK_WORDS[wordIndexRef.current],
        };

        setWords((prevWords) => [...prevWords, newWord]);
        wordIndexRef.current += 1;
      } else {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
        }
        setIsListening(false);
      }
    }, 1500);
  };

  return (
    <div className={styles.container}>
      <div className={styles.captionBox}>
        {words.length === 0 && !isListening ? (
          <div className={styles.placeholder}>
            <p className={styles.placeholderText}>Listening for ASL input...</p>
          </div>
        ) : (
          <div className={styles.captionsWrapper}>
            {words.map((word) => (
              <span
                key={word.id}
                className={styles.word}
              >
                {word.text}
              </span>
            ))}
          </div>
        )}
      </div>

      {isListening && (
        <div className={styles.indicator}>
          <div className={styles.dot} />
          <span className={styles.indicatorText}>Listening...</span>
        </div>
      )}

      <button
        onClick={handleReset}
        className={styles.resetButton}
        aria-label="Reset caption stream"
      >
        Reset Captions
      </button>
    </div>
  );
};

export default LiveCaptionDisplay;
