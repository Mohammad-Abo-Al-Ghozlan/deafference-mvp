# Gloss Buffer & Data Stabilization System

## Overview

A production-ready **Gloss Buffer** and **Debounce System** for stabilizing real-time sign language recognition streams. This system provides:

- ✅ **Raw Token Buffering** - Accumulates consecutive sign predictions
- ✅ **De-duplication** - Filters consecutive identical signs
- ✅ **Configurable Debounce** - Finalizes words after silence (default 1200ms)
- ✅ **Majority Voting** - Resolves buffer into final word using consensus
- ✅ **Confidence Filtering** - Accepts only high-confidence predictions
- ✅ **Event System** - Emits real-time events for UI updates
- ✅ **Zero External Dependencies** - Pure React hooks, standard TypeScript

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Mock Event Stream (KAN-14)                   │
│                  SIGN_RECOGNIZED / SIGN_DISCARDED                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
                  ┌─────────────────────┐
                  │  useSignRecognition │
                  │     Pipeline        │
                  │   (integration)     │
                  └──────────┬──────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
            ┌──────────────┐   ┌──────────────┐
            │ useGlossBuffer│   │useMockEvent  │
            │   (buffer)    │   │Generator     │
            └──────┬───────┘   └──────────────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
    ┌─────────┐ ┌────────┐ ┌─────────────┐
    │Gloss    │ │Debounce│ │Confidence   │
    │Buffer   │ │Timer   │ │Filter       │
    └────┬────┘ └────┬───┘ └─────────────┘
         │           │
         └─────┬─────┘
               ▼
        ┌─────────────────┐
        │ Stabilized      │
        │ Sentence Output │
        └─────────────────┘
```

## File Structure

```
hooks/
├── useGlossBuffer.ts              # Main hook: buffer + debounce logic
├── useMockEventGenerator.ts        # (existing) Mock ML event stream
└── useSignRecognitionPipeline.ts   # Integration hook combining both

reducers/
└── glossBufferReducer.ts          # Alternative: useReducer pattern

types/
├── gloss-buffer.ts                # Type definitions
└── mock-events.ts                 # (existing) Mock event types

components/deafference/
└── SignRecognitionStreamDisplay.tsx # Example UI component
```

## Quick Start

### 1. Basic Usage with Hook

```typescript
import { useGlossBuffer } from '@/hooks/useGlossBuffer';

function MyComponent() {
  const { state, addToken, getSentenceString, resetSentence } = useGlossBuffer({
    debounceConfig: {
      debounceTimeoutMs: 1200,
      confidenceThreshold: 0.7,
      maxBufferSize: 5,
      enableDuplication: false,
    },
    onSentenceUpdate: (sentence) => console.log('Final:', sentence.join(' ')),
  });

  return (
    <div>
      <p>Sentence: {getSentenceString()}</p>
      <p>Buffer: {state.glossBuffer.length} tokens</p>
      <button onClick={resetSentence}>Clear</button>
    </div>
  );
}
```

### 2. Integration with Mock Events

```typescript
import { useSignRecognitionPipeline } from '@/hooks/useSignRecognitionPipeline';

function RecognitionApp() {
  const {
    glossBufferState,
    getSentenceString,
    toggleSimulation,
    isSimulating,
    eventCount,
  } = useSignRecognitionPipeline();

  return (
    <div>
      <p>Sentence: {getSentenceString()}</p>
      <p>Status: {glossBufferState.bufferStatus}</p>
      <p>Events: {eventCount}</p>
      <button onClick={toggleSimulation}>
        {isSimulating ? 'Stop' : 'Start'}
      </button>
    </div>
  );
}
```

### 3. Use the Example Component

```typescript
import { SignRecognitionStreamDisplay } from '@/components/deafference/SignRecognitionStreamDisplay';

export default function Page() {
  return <SignRecognitionStreamDisplay showDebug />;
}
```

## API Reference

### `useGlossBuffer(config?)`

Main hook for managing gloss buffer and sign stabilization.

#### Parameters

```typescript
interface UseGlossBufferConfig {
  debounceConfig?: Partial<DebounceConfig>;
  onEvent?: (event: GlossBufferEvent) => void;
  onSentenceUpdate?: (sentence: string[]) => void;
}
```

#### Returns

```typescript
interface UseGlossBufferReturn {
  state: GlossBufferState;
  addToken: (token: GlossToken) => void;
  finalizeBuffer: () => void;
  clearBuffer: () => void;
  resetSentence: () => void;
  getSentenceString: () => string;
  updateConfig: (config: Partial<DebounceConfig>) => void;
}
```

#### Methods

| Method | Purpose | Example |
|--------|---------|---------|
| `addToken(token)` | Add recognized sign to buffer | `addToken({ label: 'Hello', confidence: 0.95, timestamp })` |
| `finalizeBuffer()` | Manually finalize current buffer to word | `finalizeBuffer()` |
| `clearBuffer()` | Clear buffer without finalizing | `clearBuffer()` |
| `resetSentence()` | Clear everything, start fresh | `resetSentence()` |
| `getSentenceString()` | Get final sentence as string | `const sentence = getSentenceString()` |
| `updateConfig(cfg)` | Update debounce config at runtime | `updateConfig({ debounceTimeoutMs: 2000 })` |

#### State

```typescript
interface GlossBufferState {
  glossBuffer: GlossToken[];              // Raw predicted tokens
  stabilizedSentence: string[];           // Final assembled words
  bufferStatus: 'idle' | 'accumulating' | 'debouncing';
  averageConfidence: number;              // 0-1
  lastSignTimestamp: number | null;       // ms since epoch
  totalSignsProcessed: number;            // Lifetime count
  totalWordsFinalized: number;            // Words added to sentence
}
```

### `useSignRecognitionPipeline()`

Integration hook combining buffer + mock event generator.

```typescript
const {
  // Buffer methods/state
  glossBufferState,
  addToken,
  finalizeBuffer,
  clearBuffer,
  resetSentence,
  getSentenceString,
  updateBufferConfig,

  // Mock event methods/state
  isSimulating,
  toggleSimulation,
  startSimulation,
  stopSimulation,
  eventCount,
} = useSignRecognitionPipeline();
```

## Configuration

### DebounceConfig

```typescript
interface DebounceConfig {
  // Time (ms) to wait before finalizing buffer
  debounceTimeoutMs: number;        // default: 1200

  // Minimum confidence (0-1) to accept a token
  confidenceThreshold: number;      // default: 0.7

  // Max tokens before auto-finalize
  maxBufferSize: number;            // default: 5

  // Filter consecutive identical signs
  enableDuplication: boolean;       // default: false
}
```

### Tuning Recommendations

| Scenario | debounceTimeoutMs | confidenceThreshold | maxBufferSize |
|----------|-------------------|-------------------|---------------|
| Fast speech | 800ms | 0.75 | 4 |
| Normal | 1200ms | 0.70 | 5 |
| Careful articulation | 1500ms | 0.65 | 6 |
| High precision | 1000ms | 0.85 | 3 |

## Events

The buffer emits real-time events for UI updates and logging:

```typescript
onEvent: (event: GlossBufferEvent) => {
  switch (event.type) {
    case 'TOKEN_RECEIVED':
      // New token added: { token, bufferSize }
      break;
    case 'WORD_FINALIZED':
      // Buffer converted to word: { word, confidence, tokenCount }
      break;
    case 'DUPLICATE_SKIPPED':
      // Consecutive duplicate filtered: { label }
      break;
    case 'BUFFER_CLEARED':
      // Buffer reset: { reason: 'reset' | 'manual_clear' | 'debounce_complete' }
      break;
    case 'SENTENCE_RESET':
      // Full reset triggered
      break;
  }
}
```

## Reducer Pattern (Alternative)

For Redux or state machine integration:

```typescript
import { useReducer } from 'react';
import { glossBufferReducer, initialGlossBufferState } from '@/reducers/glossBufferReducer';

function Component() {
  const [state, dispatch] = useReducer(glossBufferReducer, initialGlossBufferState);

  const handleSignRecognized = (token: GlossToken) => {
    dispatch({
      type: 'ADD_TOKEN',
      token,
      config: debounceConfig,
    });
  };

  return (
    <div>
      <p>Sentence: {state.stabilizedSentence.join(' ')}</p>
      <button onClick={() => dispatch({ type: 'RESET_SENTENCE' })}>
        Reset
      </button>
    </div>
  );
}
```

## How It Works

### 1. Token Reception & Buffering

```
INPUT: SIGN_RECOGNIZED { label: 'Hello', confidence: 0.95 }
                                    │
                                    ▼
                        Check confidence >= 0.7? ✓
                                    │
                                    ▼
                        Check for duplicate? ✗
                                    │
                                    ▼
                        → Add to glossBuffer
                        → Reset debounce timer
```

### 2. Debounce Logic

```
TIME_0ms:   'Hello' received     → Start 1200ms timer
TIME_150ms: 'Hello' received     → Restart 1200ms timer (duplicate)
TIME_400ms: 'World' received     → Restart 1200ms timer
TIME_1600ms:No new signs for 1200ms
                                → Finalize buffer
                                → majority_vote(['World'])
                                → Append 'World' to sentence
                                → Clear buffer
```

### 3. Finalization (Majority Voting)

```
Buffer: ['Help', 'Help', 'Help', 'Help']
        
Voting:
  'help' → 4 votes (100%)
  
Result: 'Help' added to sentence
```

```
Buffer: ['Help', 'Hello', 'Help', 'Help']

Voting:
  'help' → 3 votes (75%)
  'hello' → 1 vote (25%)

Result: 'Help' added to sentence (winner)
```

## Integration with UI Controls

### Clear Buffer Button

```typescript
<button onClick={clearBuffer}>
  Clear Buffer
</button>
```

Clears current tokens without finalizing. Useful if recognizer gives false positives.

### Reset Sentence Button

```typescript
<button onClick={resetSentence}>
  Reset All
</button>
```

Completely resets everything to initial state.

### Dynamic Debounce Tuning

```typescript
<input
  type="range"
  min="500"
  max="3000"
  value={debounceMs}
  onChange={(e) => updateConfig({ debounceTimeoutMs: parseInt(e.target.value) })}
/>
```

Adjust debounce at runtime for different sign speeds.

## Performance Considerations

- **Memory**: O(maxBufferSize) per component instance
- **CPU**: Debounce timer O(1) per token
- **No re-renders on every token**: Events dispatched, caller decides when to update
- **Zero dependencies**: Standard React hooks only

## TypeScript Support

Fully typed with strict mode support:

```typescript
// Types are exported for use in your components
import type {
  GlossBufferState,
  GlossToken,
  DebounceConfig,
  GlossBufferEvent,
  UseGlossBufferConfig,
  UseGlossBufferReturn,
} from '@/types/gloss-buffer';
```

## Examples

### Example 1: Minimal Setup

```typescript
const { state, addToken, getSentenceString } = useGlossBuffer();

// Somewhere in your event handler:
if (event.type === 'SIGN_RECOGNIZED') {
  addToken({
    label: event.payload.label,
    confidence: event.payload.confidence,
    timestamp: event.payload.timestamp,
  });
}

return <div>{getSentenceString()}</div>;
```

### Example 2: With Event Logging

```typescript
const { state, getSentenceString } = useGlossBuffer({
  onEvent: (event) => {
    if (event.type === 'WORD_FINALIZED') {
      console.log(`✓ Finalized: "${event.word}" (${(event.confidence * 100).toFixed(1)}%)`);
    } else if (event.type === 'BUFFER_CLEARED') {
      console.log(`🔄 Buffer cleared (${event.reason})`);
    }
  },
});
```

### Example 3: Full React Component

See [SignRecognitionStreamDisplay.tsx](./components/deafference/SignRecognitionStreamDisplay.tsx) for a complete production-ready component with UI controls.

## Testing

### Unit Test Example

```typescript
import { renderHook, act } from '@testing-library/react';
import { useGlossBuffer } from '@/hooks/useGlossBuffer';

it('debounces and finalizes buffer', async () => {
  jest.useFakeTimers();
  const { result } = renderHook(() =>
    useGlossBuffer({ debounceConfig: { debounceTimeoutMs: 1000 } })
  );

  act(() => {
    result.current.addToken({
      label: 'Hello',
      confidence: 0.9,
      timestamp: Date.now(),
    });
  });

  expect(result.current.state.glossBuffer).toHaveLength(1);

  act(() => {
    jest.advanceTimersByTime(1100);
  });

  expect(result.current.state.stabilizedSentence).toContain('hello');
  expect(result.current.state.glossBuffer).toHaveLength(0);

  jest.useRealTimers();
});
```

## Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| Words not finalizing | Debounce timeout too long | Reduce `debounceTimeoutMs` |
| Too many false positives | Confidence threshold too low | Increase `confidenceThreshold` |
| Duplicate signs accumulate | `enableDuplication` is true | Set to `false` |
| Buffer fills up | `maxBufferSize` too small | Increase `maxBufferSize` |

## Roadmap

- [ ] Persistence (localStorage for session state)
- [ ] Analytics (tracks user patterns)
- [ ] Undo/Redo for sentence editing
- [ ] Multi-language sentence tokenization
- [ ] WebWorker offloading for large streams

---

**Created for the Deafference Sign Language AI platform**
Designed for production use with enterprise-grade reliability.
