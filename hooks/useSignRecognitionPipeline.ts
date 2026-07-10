/**
 * Integration Example: useGlossBuffer + useMockEventGenerator
 * Shows how to wire the gloss buffer into your sign recognition pipeline
 */

'use client';

import { useCallback, useEffect } from 'react';
import { useGlossBuffer } from '@/hooks/useGlossBuffer';
import { useMockEventGenerator } from '@/hooks/useMockEventGenerator';
import { MockEvent } from '@/types/mock-events';
import { GlossToken } from '@/types/gloss-buffer';

/**
 * Integration hook that connects mock events to gloss buffer
 *
 * @example
 * // In your component:
 * const { state, getSentenceString, clearBuffer, resetSentence, isSimulating, toggleSimulation } =
 *   useSignRecognitionPipeline();
 *
 * return (
 *   <div>
 *     <p>Current Sentence: {getSentenceString()}</p>
 *     <p>Buffer Status: {state.bufferStatus}</p>
 *     <button onClick={clearBuffer}>Clear Buffer</button>
 *     <button onClick={resetSentence}>Reset Sentence</button>
 *     <button onClick={toggleSimulation}>
 *       {isSimulating ? 'Stop' : 'Start'} Recognition
 *     </button>
 *   </div>
 * );
 */
export const useSignRecognitionPipeline = () => {
  // Initialize gloss buffer with custom config
  const glossBuffer = useGlossBuffer({
    debounceConfig: {
      debounceTimeoutMs: 1200,
      confidenceThreshold: 0.7,
      maxBufferSize: 5,
      enableDuplication: false,
    },
    onEvent: (event) => {
      console.log('[GlossBuffer Event]', event.type, event);
    },
    onSentenceUpdate: (sentence) => {
      console.log('[Sentence Updated]', sentence.join(' '));
    },
  });

  // Handle mock event stream
  const handleMockEvent = useCallback(
    (event: MockEvent) => {
      if (event.type === 'SIGN_RECOGNIZED') {
        // Extract payload and convert to GlossToken
        const payload = event.payload as any;
        const token: GlossToken = {
          label: payload.label,
          confidence: payload.confidence,
          timestamp: payload.timestamp,
        };

        console.log('[Sign Recognized]', token.label, `(${(token.confidence * 100).toFixed(1)}%)`);

        // Add to buffer
        glossBuffer.addToken(token);
      } else if (event.type === 'SIGN_DISCARDED') {
        const payload = event.payload as any;
        console.log(
          '[Sign Discarded]',
          payload.reason,
          `(confidence: ${(payload.confidence * 100).toFixed(1)}%)`
        );
      }
    },
    [glossBuffer]
  );

  // Initialize mock event generator
  const {
    isSimulating,
    toggleSimulation,
    eventCount,
    startSimulation,
    stopSimulation,
  } = useMockEventGenerator({
    intervalMs: 3500,
    onEvent: handleMockEvent,
    autoStart: false,
  });

  return {
    // Gloss buffer methods and state
    glossBufferState: glossBuffer.state,
    addToken: glossBuffer.addToken,
    finalizeBuffer: glossBuffer.finalizeBuffer,
    clearBuffer: glossBuffer.clearBuffer,
    resetSentence: glossBuffer.resetSentence,
    getSentenceString: glossBuffer.getSentenceString,
    updateBufferConfig: glossBuffer.updateConfig,

    // Mock generator methods and state
    isSimulating,
    toggleSimulation,
    startSimulation,
    stopSimulation,
    eventCount,
  };
};

export default useSignRecognitionPipeline;
