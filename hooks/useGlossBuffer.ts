/**
 * useGlossBuffer Hook
 * Production-ready gloss buffer and stabilization layer for sign language recognition
 * Handles token accumulation, de-duplication, debouncing, and sentence assembly
 */

'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  GlossBufferState,
  GlossToken,
  DebounceConfig,
  GlossBufferEvent,
  UseGlossBufferConfig,
  UseGlossBufferReturn,
} from '@/types/gloss-buffer';

const DEFAULT_DEBOUNCE_CONFIG: DebounceConfig = {
  debounceTimeoutMs: 1200,
  confidenceThreshold: 0.7,
  maxBufferSize: 5,
  enableDuplication: false,
};

/**
 * Calculate average confidence from token array
 */
const calculateAverageConfidence = (tokens: GlossToken[]): number => {
  if (tokens.length === 0) return 0;
  const sum = tokens.reduce((acc, token) => acc + token.confidence, 0);
  return sum / tokens.length;
};

/**
 * Check if current token is a duplicate of the last token in buffer
 */
const isDuplicate = (token: GlossToken, lastToken: GlossToken | null): boolean => {
  if (!lastToken) return false;
  return token.label.toLowerCase() === lastToken.label.toLowerCase();
};

/**
 * Convert buffer tokens to a finalized word string
 * Takes the most common label or uses majority voting
 */
const finalizeBufferToWord = (tokens: GlossToken[]): { word: string; confidence: number } => {
  if (tokens.length === 0) {
    return { word: '', confidence: 0 };
  }

  // Count occurrences of each label
  const labelCounts: Record<string, number> = {};
  tokens.forEach((token) => {
    const normalized = token.label.toLowerCase();
    labelCounts[normalized] = (labelCounts[normalized] || 0) + 1;
  });

  // Find most common label
  const mostCommonLabel = Object.entries(labelCounts).reduce((a, b) =>
    b[1] > a[1] ? b : a
  )[0];

  // Average confidence of that label's occurrences
  const relevantTokens = tokens.filter(
    (t) => t.label.toLowerCase() === mostCommonLabel
  );
  const confidence = calculateAverageConfidence(relevantTokens);

  return { word: mostCommonLabel, confidence };
};

/**
 * Custom hook for managing gloss buffer and sign stabilization
 *
 * @example
 * const { state, addToken, finalizeBuffer, getSentenceString, resetSentence } = useGlossBuffer({
 *   debounceConfig: { debounceTimeoutMs: 1500 },
 *   onSentenceUpdate: (sentence) => console.log('Sentence:', sentence.join(' ')),
 * });
 *
 * // In event handler:
 * if (event.type === 'SIGN_RECOGNIZED') {
 *   addToken({
 *     label: event.payload.label,
 *     confidence: event.payload.confidence,
 *     timestamp: event.payload.timestamp,
 *   });
 * }
 */
export const useGlossBuffer = (
  config?: UseGlossBufferConfig
): UseGlossBufferReturn => {
  const { debounceConfig: customConfig, onEvent, onSentenceUpdate } = config || {};

  // Merge with defaults
  const [debounceConfig, setDebounceConfig] = useState<DebounceConfig>({
    ...DEFAULT_DEBOUNCE_CONFIG,
    ...customConfig,
  });

  // Main state
  const [state, setState] = useState<GlossBufferState>({
    glossBuffer: [],
    stabilizedSentence: [],
    bufferStatus: 'idle',
    averageConfidence: 0,
    lastSignTimestamp: null,
    totalSignsProcessed: 0,
    totalWordsFinalized: 0,
  });

  // Refs for debounce and event tracking
  const debounceTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const onEventRef = useRef<((event: GlossBufferEvent) => void) | undefined>(onEvent);
  const onSentenceUpdateRef = useRef<
    ((sentence: string[]) => void) | undefined
  >(onSentenceUpdate);

  // Keep refs in sync with latest callbacks
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    onSentenceUpdateRef.current = onSentenceUpdate;
  }, [onSentenceUpdate]);

  /**
   * Emit an event (internal use)
   */
  const emitEvent = useCallback((event: GlossBufferEvent) => {
    onEventRef.current?.(event);
  }, []);

  /**
   * Finalize the current buffer by converting it to a word and appending to sentence
   */
  const finalizeBuffer = useCallback(() => {
    setState((prev) => {
      if (prev.glossBuffer.length === 0) {
        return prev;
      }

      const { word, confidence } = finalizeBufferToWord(prev.glossBuffer);

      if (!word) {
        return prev;
      }

      const newSentence = [...prev.stabilizedSentence, word];

      emitEvent({
        type: 'WORD_FINALIZED',
        word,
        confidence,
        tokenCount: prev.glossBuffer.length,
      });

      onSentenceUpdateRef.current?.(newSentence);

      return {
        ...prev,
        glossBuffer: [],
        stabilizedSentence: newSentence,
        bufferStatus: 'idle',
        averageConfidence: 0,
        totalWordsFinalized: prev.totalWordsFinalized + 1,
      };
    });

    // Clear debounce timeout
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
      debounceTimeoutRef.current = null;
    }
  }, [emitEvent]);

  /**
   * Clear the buffer without finalizing
   */
  const clearBuffer = useCallback(() => {
    setState((prev) => {
      if (prev.glossBuffer.length === 0) {
        return prev;
      }

      emitEvent({
        type: 'BUFFER_CLEARED',
        reason: 'manual_clear',
      });

      return {
        ...prev,
        glossBuffer: [],
        bufferStatus: 'idle',
        averageConfidence: 0,
      };
    });

    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
      debounceTimeoutRef.current = null;
    }
  }, [emitEvent]);

  /**
   * Reset the entire sentence
   */
  const resetSentence = useCallback(() => {
    setState((prev) => ({
      ...prev,
      glossBuffer: [],
      stabilizedSentence: [],
      bufferStatus: 'idle',
      averageConfidence: 0,
      lastSignTimestamp: null,
      totalSignsProcessed: 0,
      totalWordsFinalized: 0,
    }));

    onSentenceUpdateRef.current?.([]);
    emitEvent({ type: 'SENTENCE_RESET' });

    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
      debounceTimeoutRef.current = null;
    }
  }, [emitEvent]);

  /**
   * Add a token to the buffer with debounce logic
   */
  const addToken = useCallback(
    (token: GlossToken) => {
      // Filter by confidence threshold
      if (token.confidence < debounceConfig.confidenceThreshold) {
        return;
      }

      setState((prev) => {
        const lastToken = prev.glossBuffer[prev.glossBuffer.length - 1] || null;

        // Check for duplicates
        if (
          debounceConfig.enableDuplication &&
          isDuplicate(token, lastToken)
        ) {
          emitEvent({
            type: 'DUPLICATE_SKIPPED',
            label: token.label,
          });
          return prev;
        }

        // Add token to buffer
        const newBuffer = [...prev.glossBuffer, token];

        // Check if buffer exceeds max size
        if (newBuffer.length > debounceConfig.maxBufferSize) {
          // Auto-finalize
          const { word, confidence: wordConfidence } =
            finalizeBufferToWord(newBuffer);

          const newSentence = [...prev.stabilizedSentence, word];

          emitEvent({
            type: 'WORD_FINALIZED',
            word,
            confidence: wordConfidence,
            tokenCount: newBuffer.length,
          });

          onSentenceUpdateRef.current?.(newSentence);

          emitEvent({
            type: 'TOKEN_RECEIVED',
            token,
            bufferSize: 1, // Reset to 1 for next cycle
          });

          return {
            ...prev,
            glossBuffer: [],
            stabilizedSentence: newSentence,
            bufferStatus: 'idle',
            averageConfidence: 0,
            lastSignTimestamp: token.timestamp,
            totalSignsProcessed: prev.totalSignsProcessed + 1,
            totalWordsFinalized: prev.totalWordsFinalized + 1,
          };
        }

        emitEvent({
          type: 'TOKEN_RECEIVED',
          token,
          bufferSize: newBuffer.length,
        });

        // Update average confidence
        const avgConfidence = calculateAverageConfidence(newBuffer);

        return {
          ...prev,
          glossBuffer: newBuffer,
          bufferStatus: 'accumulating',
          averageConfidence: avgConfidence,
          lastSignTimestamp: token.timestamp,
          totalSignsProcessed: prev.totalSignsProcessed + 1,
        };
      });

      // Reset debounce timer
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current);
      }

      debounceTimeoutRef.current = setTimeout(() => {
        finalizeBuffer();
        emitEvent({ type: 'BUFFER_CLEARED', reason: 'debounce_complete' });
      }, debounceConfig.debounceTimeoutMs);
    },
    [debounceConfig, emitEvent, finalizeBuffer]
  );

  /**
   * Get the current sentence as a single string
   */
  const getSentenceString = useCallback(() => {
    return state.stabilizedSentence.join(' ');
  }, [state.stabilizedSentence]);

  /**
   * Update debounce configuration at runtime
   */
  const updateConfig = useCallback((config: Partial<DebounceConfig>) => {
    setDebounceConfig((prev) => ({
      ...prev,
      ...config,
    }));
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current);
      }
    };
  }, []);

  return {
    state,
    addToken,
    finalizeBuffer,
    clearBuffer,
    resetSentence,
    getSentenceString,
    updateConfig,
  };
};

export default useGlossBuffer;
