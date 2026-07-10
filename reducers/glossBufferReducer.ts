/**
 * Gloss Buffer State Machine (Reducer Pattern)
 * Alternative implementation using useReducer for state management
 * Useful if you're using Redux or a state machine library
 */

import { GlossBufferState, GlossToken, DebounceConfig, GlossBufferEvent } from '@/types/gloss-buffer';

export type GlossBufferAction =
  | {
      type: 'ADD_TOKEN';
      token: GlossToken;
      config: DebounceConfig;
    }
  | {
      type: 'FINALIZE_BUFFER';
    }
  | {
      type: 'CLEAR_BUFFER';
    }
  | {
      type: 'RESET_SENTENCE';
    }
  | {
      type: 'SET_BUFFER_STATUS';
      status: 'idle' | 'accumulating' | 'debouncing';
    };

/**
 * Pure reducer function for gloss buffer state management
 * Can be used with useReducer hook or integrated into Redux
 *
 * @example
 * const [state, dispatch] = useReducer(glossBufferReducer, initialState);
 *
 * // Add token:
 * dispatch({
 *   type: 'ADD_TOKEN',
 *   token: { label: 'Hello', confidence: 0.95, timestamp: Date.now() },
 *   config: debounceConfig,
 * });
 */
export const glossBufferReducer = (
  state: GlossBufferState,
  action: GlossBufferAction
): GlossBufferState => {
  switch (action.type) {
    case 'ADD_TOKEN': {
      const { token, config } = action;

      // Filter by confidence threshold
      if (token.confidence < config.confidenceThreshold) {
        return state;
      }

      const lastToken = state.glossBuffer[state.glossBuffer.length - 1] || null;

      // Check for duplicates (optional)
      if (
        config.enableDuplication &&
        lastToken &&
        token.label.toLowerCase() === lastToken.label.toLowerCase()
      ) {
        return state;
      }

      // Add token to buffer
      const newBuffer = [...state.glossBuffer, token];

      // Calculate average confidence
      const avgConfidence =
        newBuffer.reduce((sum, t) => sum + t.confidence, 0) / newBuffer.length;

      // Check if buffer exceeds max size
      if (newBuffer.length > config.maxBufferSize) {
        // Auto-finalize: find most common label
        const labelCounts: Record<string, number> = {};
        newBuffer.forEach((t) => {
          const normalized = t.label.toLowerCase();
          labelCounts[normalized] = (labelCounts[normalized] || 0) + 1;
        });

        const mostCommonLabel = Object.entries(labelCounts).reduce((a, b) =>
          b[1] > a[1] ? b : a
        )[0];

        const newSentence = [...state.stabilizedSentence, mostCommonLabel];

        return {
          ...state,
          glossBuffer: [],
          stabilizedSentence: newSentence,
          bufferStatus: 'idle',
          averageConfidence: 0,
          lastSignTimestamp: token.timestamp,
          totalSignsProcessed: state.totalSignsProcessed + 1,
          totalWordsFinalized: state.totalWordsFinalized + 1,
        };
      }

      return {
        ...state,
        glossBuffer: newBuffer,
        bufferStatus: 'accumulating',
        averageConfidence: avgConfidence,
        lastSignTimestamp: token.timestamp,
        totalSignsProcessed: state.totalSignsProcessed + 1,
      };
    }

    case 'FINALIZE_BUFFER': {
      if (state.glossBuffer.length === 0) {
        return state;
      }

      // Find most common label (majority voting)
      const labelCounts: Record<string, number> = {};
      state.glossBuffer.forEach((token) => {
        const normalized = token.label.toLowerCase();
        labelCounts[normalized] = (labelCounts[normalized] || 0) + 1;
      });

      const mostCommonLabel = Object.entries(labelCounts).reduce((a, b) =>
        b[1] > a[1] ? b : a
      )[0];

      const newSentence = [...state.stabilizedSentence, mostCommonLabel];

      return {
        ...state,
        glossBuffer: [],
        stabilizedSentence: newSentence,
        bufferStatus: 'idle',
        averageConfidence: 0,
        totalWordsFinalized: state.totalWordsFinalized + 1,
      };
    }

    case 'CLEAR_BUFFER': {
      return {
        ...state,
        glossBuffer: [],
        bufferStatus: 'idle',
        averageConfidence: 0,
      };
    }

    case 'RESET_SENTENCE': {
      return {
        glossBuffer: [],
        stabilizedSentence: [],
        bufferStatus: 'idle',
        averageConfidence: 0,
        lastSignTimestamp: null,
        totalSignsProcessed: 0,
        totalWordsFinalized: 0,
      };
    }

    case 'SET_BUFFER_STATUS': {
      return {
        ...state,
        bufferStatus: action.status,
      };
    }

    default:
      return state;
  }
};

/**
 * Initial state for gloss buffer
 */
export const initialGlossBufferState: GlossBufferState = {
  glossBuffer: [],
  stabilizedSentence: [],
  bufferStatus: 'idle',
  averageConfidence: 0,
  lastSignTimestamp: null,
  totalSignsProcessed: 0,
  totalWordsFinalized: 0,
};
