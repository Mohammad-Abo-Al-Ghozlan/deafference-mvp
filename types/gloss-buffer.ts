/**
 * Gloss Buffer & Stabilization Types
 * Handles raw sign predictions, de-duplication, and sentence assembly
 */

/**
 * Represents a single recognized sign token with metadata
 */
export interface GlossToken {
  label: string;
  confidence: number;
  timestamp: number;
}

/**
 * State of the gloss buffer system
 */
export interface GlossBufferState {
  /** Array of raw recognized tokens (not yet stabilized) */
  glossBuffer: GlossToken[];

  /** The final, cleaned sentence assembled from stabilized tokens */
  stabilizedSentence: string[];

  /** Current buffer status */
  bufferStatus: 'idle' | 'accumulating' | 'debouncing';

  /** Average confidence of current buffer */
  averageConfidence: number;

  /** Timestamp of last received sign */
  lastSignTimestamp: number | null;

  /** Total signs processed in this session */
  totalSignsProcessed: number;

  /** Total words added to final sentence */
  totalWordsFinalized: number;
}

/**
 * Debounce configuration
 */
export interface DebounceConfig {
  /** Time (ms) to wait before finalizing buffer as complete word */
  debounceTimeoutMs: number;

  /** Minimum confidence threshold to accept a token (0-1) */
  confidenceThreshold: number;

  /** Maximum tokens to accumulate in buffer before auto-finalize */
  maxBufferSize: number;

  /** Whether to de-duplicate consecutive identical signs */
  enableDuplication: boolean;
}

/**
 * Events emitted by the gloss buffer
 */
export type GlossBufferEvent =
  | {
      type: 'TOKEN_RECEIVED';
      token: GlossToken;
      bufferSize: number;
    }
  | {
      type: 'WORD_FINALIZED';
      word: string;
      confidence: number;
      tokenCount: number;
    }
  | {
      type: 'BUFFER_CLEARED';
      reason: 'reset' | 'manual_clear' | 'debounce_complete';
    }
  | {
      type: 'SENTENCE_RESET';
    }
  | {
      type: 'DUPLICATE_SKIPPED';
      label: string;
    };

/**
 * Configuration for the useGlossBuffer hook
 */
export interface UseGlossBufferConfig {
  debounceConfig?: Partial<DebounceConfig>;
  onEvent?: (event: GlossBufferEvent) => void;
  onSentenceUpdate?: (sentence: string[]) => void;
}

/**
 * Return type for useGlossBuffer hook
 */
export interface UseGlossBufferReturn {
  /** Current buffer state */
  state: GlossBufferState;

  /** Add a recognized token to the buffer */
  addToken: (token: GlossToken) => void;

  /** Manually finalize and append current buffer to sentence */
  finalizeBuffer: () => void;

  /** Clear the current buffer without finalizing */
  clearBuffer: () => void;

  /** Reset the entire sentence */
  resetSentence: () => void;

  /** Get the current sentence as a string */
  getSentenceString: () => string;

  /** Update debounce configuration at runtime */
  updateConfig: (config: Partial<DebounceConfig>) => void;
}
