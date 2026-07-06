/**
 * LiveCaptionDisplay Component
 * Real-time caption display for ASL recognition with simulated streaming transcription
 * Production-ready with full TypeScript typing and proper cleanup
 */

import React, { useState, useEffect, useCallback } from 'react';
import styles from './LiveCaptionDisplay.module.css';

// Mock words to simulate ASL recognition streaming
const MOCK_WORDS: string[] = [
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

/**
 * Interface for a single caption word with metadata
 */
interface CaptionWord {
  id: string;
  text: string;
  timestamp: number;
}

/**
 * LiveCaptionDisplay Component
 * Displays recognized words in real-time as an overlay with smooth animations
 *
 * @returns {JSX.Element} Rendered caption display component
 */
const LiveCaptionDisplay: React.FC = (): JSX.Element => {
  // State management for recognized words
  const [captionWords, setCaptionWords] = useState<CaptionWord[]>([]);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [wordIndex, setWordIndex] = useState<number>(0);

  /**
   * Generate unique ID for each caption word
   */
  const generateId = useCallback((): string => {
    return `word_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }, []);

  /**
   * Add a new word to the caption display
   */
  const addCaptionWord = useCallback((word: string): void => {
    const newWord: CaptionWord = {
      id: generateId(),
      text: word,
      timestamp: Date.now(),
    };
    setCaptionWords((prevWords: CaptionWord[]): CaptionWord[] => [
      ...prevWords,
      newWord,
    ]);
  }, [generateId]);

  /**
   * Main effect: Simulate real-time ASL transcription streaming
   * Appends a new mock word every 1.5 seconds
   */
  useEffect((): (() => void) => {
    // Start streaming
    setIsStreaming(true);

    // Set up interval to append words
    const intervalId: NodeJS.Timeout = setInterval((): void => {
      setWordIndex((prevIndex: number): number => {
        const nextIndex: number = prevIndex + 1;

        // If we haven't exhausted mock words, add the next one
        if (nextIndex <= MOCK_WORDS.length) {
          addCaptionWord(MOCK_WORDS[prevIndex]);
          return nextIndex;
        }

        // Stop streaming when all words are added
        setIsStreaming(false);
        return prevIndex;
      });
    }, 1500); // Append word every 1.5 seconds

    // Cleanup function: Clear interval on unmount or effect re-run
    return (): void => {
      clearInterval(intervalId);
    };
  }, [addCaptionWord]);

  /**
   * Render empty state when no captions have started
   */
  if (captionWords.length === 0 && !isStreaming) {
    return (
      <div className={styles.container}>
        <div className={styles.placeholder}>
          Listening for ASL input...
        </div>
      </div>
    );
  }

  /**
   * Render live captions container
   */
  return (
    <div className={styles.container}>
      <div className={styles.captionBlock}>
        {/* Empty state - showing when streaming but no words yet */}
        {captionWords.length === 0 && isStreaming && (
          <div className={styles.placeholder}>
            Listening for ASL input...
          </div>
        )}

        {/* Caption words display */}
        {captionWords.length > 0 && (
          <div className={styles.captionText}>
            {captionWords.map((word: CaptionWord, index: number): JSX.Element => (
              <span
                key={word.id}
                className={styles.word}
                style={{
                  animationDelay: `${index * 0.1}s`,
                }}
              >
                {word.text}
                {index < captionWords.length - 1 && ' '}
              </span>
            ))}
          </div>
        )}

        {/* Streaming indicator */}
        {isStreaming && (
          <div className={styles.streamingIndicator}>
            <span className={styles.dot}></span>
            <span className={styles.dot}></span>
            <span className={styles.dot}></span>
          </div>
        )}
      </div>
    </div>
  );
};

export default LiveCaptionDisplay;
