// MOCK_EVENT_GENERATOR_GUIDE.md

# MockEventGenerator Utility - Integration Guide

## Overview

The `useMockEventGenerator` hook is a production-ready utility for testing the Isolated Sign Language Recognition application without a live ML model. It simulates real-time inference events by firing fake `SIGN_RECOGNIZED` and `SIGN_DISCARDED` events on a configurable timer.

## Architecture

### Components

1. **types/mock-events.ts** - Type definitions and constants
   - `MockEvent` - Union type for all mock events
   - `SignRecognizedPayload` - Event payload for recognized signs
   - `SignDiscardedPayload` - Event payload for discarded signs
   - `MOCK_ASL_VOCABULARY` - Array of 25+ mock ASL terms
   - `DISCARD_REASONS` - Array of possible discard reasons

2. **hooks/useMockEventGenerator.ts** - Custom React hook
   - `useMockEventGenerator()` - Main hook implementation
   - Controls simulation start/stop/toggle
   - Fires alternating SIGN_RECOGNIZED and SIGN_DISCARDED events
   - Generates random confidence scores
   - Fully typed with no 'any' types

3. **components/deafference/SignLanguageStateMachineWithMock.tsx** - Integration example
   - Demonstrates full integration with state machine
   - Handles mock events and transitions states
   - Includes debug panel with mock controls
   - Shows event log of recent mock events

## Usage

### Basic Implementation

```typescript
import { useMockEventGenerator } from '@/hooks/useMockEventGenerator';
import { MockEvent } from '@/types/mock-events';

function MyComponent() {
  const handleMockEvent = (event: MockEvent) => {
    if (event.type === 'SIGN_RECOGNIZED') {
      console.log(`Sign recognized: ${event.payload.label}`);
      console.log(`Confidence: ${event.payload.confidence}`);
    } else if (event.type === 'SIGN_DISCARDED') {
      console.log(`Sign discarded: ${event.payload.reason}`);
    }
  };

  const { isSimulating, toggleSimulation, eventCount } = useMockEventGenerator({
    intervalMs: 3500,
    onEvent: handleMockEvent,
    autoStart: false,
  });

  return (
    <div>
      <button onClick={toggleSimulation}>
        {isSimulating ? 'Stop' : 'Start'} Mock Events
      </button>
      <p>Events generated: {eventCount}</p>
    </div>
  );
}
```

### With State Machine

```typescript
import SignLanguageStateMachineWithMock from '@/components/deafference/SignLanguageStateMachineWithMock';

export default function MyPage() {
  return (
    <SignLanguageStateMachineWithMock
      mockIntervalMs={3500}
      autoStartMock={false}
    />
  );
}
```

## Hook API

### useMockEventGenerator(config)

#### Parameters

```typescript
interface UseMockEventGeneratorConfig {
  intervalMs?: number;           // Event firing interval in milliseconds (default: 3500)
  onEvent: MockEventCallback;    // Callback function fired on each event
  autoStart?: boolean;           // Automatically start simulation (default: false)
}
```

#### Return Value

```typescript
interface UseMockEventGeneratorReturn {
  isSimulating: boolean;         // Current simulation state
  startSimulation: () => void;   // Start firing events
  stopSimulation: () => void;    // Stop firing events
  toggleSimulation: () => void;  // Toggle between start/stop
  eventCount: number;            // Total events generated
}
```

## Event Types

### SIGN_RECOGNIZED Event

Fired when the mock generator simulates successful sign detection.

```typescript
{
  type: 'SIGN_RECOGNIZED',
  payload: {
    label: 'Hello',              // One of 25+ mock ASL terms
    confidence: 0.92,            // Random score between 0.75 - 0.99
    timestamp: 1720285456789,    // Event timestamp
  }
}
```

### SIGN_DISCARDED Event

Fired when the mock generator simulates a failed sign detection.

```typescript
{
  type: 'SIGN_DISCARDED',
  payload: {
    reason: 'low_confidence',    // One of 4 discard reasons
    confidence: 0.35,            // Random score between 0.15 - 0.50
    timestamp: 1720285456789,    // Event timestamp
  }
}
```

## Mock ASL Vocabulary

The following 25 terms are randomly selected for SIGN_RECOGNIZED events:

```
Hello, Thank you, Please, Good morning, Good night, Help, Water, Food,
Bathroom, Goodbye, Yes, No, More, Stop, Sorry, Welcome, Friend, Family,
Love, Happy, Sad, Tired, Hungry, Beautiful, Important
```

## Discard Reasons

When SIGN_DISCARDED events are fired, one of these reasons is randomly selected:

```
- low_confidence       // Confidence score too low
- gesture_incomplete   // Hand gesture not fully completed
- no_hand_detected     // No hands visible in frame
- multiple_hands       // Multiple hands detected
```

## State Machine Integration

When integrated with `SignLanguageStateMachine`, the mock event generator:

1. Fires alternating SIGN_RECOGNIZED and SIGN_DISCARDED events every 3-4 seconds
2. SIGN_RECOGNIZED events trigger state transition to `sign_recognized` with recognized label
3. SIGN_DISCARDED events trigger state transition to `error` with discard reason
4. Debug panel displays:
   - Toggle button to start/stop mock events
   - Running status indicator
   - Event counter
   - Recent event log (last 10 events)

## Advanced Configuration

### Custom Interval

```typescript
const { isSimulating, toggleSimulation } = useMockEventGenerator({
  intervalMs: 2000,  // Fire events every 2 seconds
  onEvent: handleMockEvent,
});
```

### Auto-start Simulation

```typescript
const { isSimulating } = useMockEventGenerator({
  intervalMs: 3500,
  onEvent: handleMockEvent,
  autoStart: true,  // Start immediately
});
```

### Event Filtering

```typescript
const handleMockEvent = (event: MockEvent) => {
  if (event.type === 'SIGN_RECOGNIZED') {
    const payload = event.payload as SignRecognizedPayload;
    // Only process high-confidence signs
    if (payload.confidence > 0.85) {
      processRecognizedSign(payload.label);
    }
  }
};

useMockEventGenerator({
  intervalMs: 3500,
  onEvent: handleMockEvent,
});
```

## Type Safety

All aspects of the hook are fully typed with strict TypeScript:

```typescript
// Type-safe event handling
const handleMockEvent = (event: MockEvent): void => {
  switch (event.type) {
    case 'SIGN_RECOGNIZED': {
      const payload = event.payload as SignRecognizedPayload;
      console.log(payload.label);      // ✓ autocomplete works
      console.log(payload.confidence); // ✓ type checked
      break;
    }
    case 'SIGN_DISCARDED': {
      const payload = event.payload as SignDiscardedPayload;
      console.log(payload.reason);     // ✓ autocomplete works
      console.log(payload.confidence); // ✓ type checked
      break;
    }
  }
};

// No 'any' types - full IDE support throughout
```

## Lifecycle Management

The hook handles cleanup automatically:

- Events stop firing when component unmounts
- Intervals are properly cleared
- No memory leaks or dangling references
- Safe to mount/unmount multiple instances

```typescript
// Component lifecycle - no manual cleanup needed
useEffect(() => {
  const { isSimulating, toggleSimulation } = useMockEventGenerator({
    intervalMs: 3500,
    onEvent: handleMockEvent,
  });

  // Hook handles cleanup on unmount automatically
}, []);
```

## Testing Workflows

### QA Testing Workflow

1. Navigate to `/mock-testing-demo`
2. Click "Start Mock Events" button
3. Watch state machine transitions through different states
4. Observe event log at bottom of debug panel
5. Click "Stop Mock Events" to halt simulation
6. Verify state machine responsiveness

### Manual State Transitions

While mock events are running:

1. Use debug buttons to manually force specific states
2. Observe how state transitions work with concurrent events
3. Test error handling and recovery flows
4. Validate UI responsiveness under event load

### Performance Validation

- Monitor browser console for any warnings/errors
- Check event processing speed (should be < 100ms)
- Validate no memory leaks over extended test sessions
- Test with different interval values

## File Structure

```
hooks/
  └── useMockEventGenerator.ts

types/
  └── mock-events.ts

components/deafference/
  ├── SignLanguageStateMachineWithMock.tsx
  └── SignLanguageStateMachine.module.css (updated)

app/
  └── mock-testing-demo/
      └── page.tsx
```

## Code Quality Checklist

✅ Strict TypeScript typing throughout (no 'any' types)
✅ No placeholder 'TODO' comments
✅ Comprehensive event type definitions
✅ Proper React hook lifecycle management
✅ Automatic cleanup on unmount
✅ Separated business logic from UI
✅ Fully documented with JSDoc comments
✅ Production-ready error handling
✅ No external dependencies beyond React

## Summary

The `useMockEventGenerator` hook provides a clean, type-safe way to test the sign language recognition application without a live ML model. It integrates seamlessly with the state machine and provides QA teams with intuitive controls for simulating real-world scenarios.
