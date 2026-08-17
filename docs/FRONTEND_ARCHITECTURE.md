# Sign Language Recognition - Frontend State Machine Architecture

## Overview

This document describes the robust, type-safe State Machine architecture for the Sign Language Recognition application built with React and TypeScript.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    SignLanguageApp (Main)                       │
│                                                                 │
│  State: 'permission_needed' | 'loading_model' | 'listening' │
│         | 'sign_recognized' | 'speaking' | 'error'            │
│                                                                 │
│  Context Data:                                                  │
│  - recognizedSign: string | null                               │
│  - errorMessage: string | null                                 │
│  - audioWaveform: number[]                                     │
└─────────────────────────────────────────────────────────────────┘
         ↓
    renderCurrentScreen()
         ↓
    ┌─────────────────────────────────────────────────────────────┐
    │                    State Screens                            │
    ├─────────────────────────────────────────────────────────────┤
    │  1. PermissionNeededScreen                                 │
    │  2. LoadingModelScreen                                     │
    │  3. ListeningScreen                                        │
    │  4. SignRecognizedScreen                                   │
    │  5. SpeakingScreen                                         │
    │  6. ErrorScreen                                            │
    └─────────────────────────────────────────────────────────────┘
         ↓
    ┌─────────────────────────────────────────────────────────────┐
    │            Dev Control Panel (Bottom Fixed)                 │
    │                                                              │
    │  Buttons for testing each state instantly                   │
    └─────────────────────────────────────────────────────────────┘
```

## State Machine Definition

### Type Safety

```typescript
type AppState = 
  | 'permission_needed'    // Initial state - requires camera permission
  | 'loading_model'        // Model initializing
  | 'listening'            // Active recognition mode
  | 'sign_recognized'      // Sign detected, awaiting TTS
  | 'speaking'             // Text-to-speech audio playback
  | 'error';               // Error state with recovery
```

### State Transitions

```
permission_needed
      ↓
   (user grants permission)
      ↓
loading_model
      ↓
   (model loaded)
      ↓
listening ←──────┐
      ↓          │
(sign detected)  │
      ↓          │
sign_recognized  │
      ↓          │
(speak)          │
      ↓          │
speaking         │
      ↓          │
(audio complete)─┘

Any State ──(error)──→ error ──(retry)──→ listening
```

## File Structure

```
src/
├── components/
│   └── SignLanguageApp.tsx          # Main state machine component
│       ├── Type Definitions
│       ├── State Components (6 screens)
│       ├── Dev Control Panel
│       ├── Main App Component
│       └── Styles
└── App.tsx                          # React app wrapper
```

## Component Details

### 1. PermissionNeededScreen

**Purpose:** Request camera permission from user

**Props:**
- `onGrantPermission: () => void` - Called when user clicks "Grant Permission"

**Visual Elements:**
- Camera icon (📷)
- Feature list (3 bullet points)
- CTA button: "Grant Camera Permission"
- Privacy notice

**Behavior:**
- Explains why camera is needed
- Lists benefits
- Large, prominent CTA button

---

### 2. LoadingModelScreen

**Purpose:** Display loading state while ML model initializes

**Props:** None

**Visual Elements:**
- Animated spinner
- Loading steps (3 phases)
- Status message

**Animation:**
- Continuous rotation (0.8s cycle)

**Behavior:**
- Shows initialization progress
- Auto-transitions to 'listening' (simulated in dev)

---

### 3. ListeningScreen

**Purpose:** Main camera feed with real-time recognition UI

**Props:** None

**Visual Elements:**
- Black camera placeholder with scanning animation
- Green corner markers (┌ ┐ └ ┘)
- Scanning line animation (top to bottom)
- Pulsing status indicator
- "Listening..." text
- Instructions

**Animations:**
- Horizontal scanning line (2s cycle)
- Pulsing dot (1s cycle)
- Green glow effects

**Behavior:**
- Main recognition screen
- Ready to accept gesture input

---

### 4. SignRecognizedScreen

**Purpose:** Display recognized sign with confidence

**Props:**
- `recognizedSign: string | null` - The detected sign text
- `onContinue: () => void` - Called when user clicks action button

**Visual Elements:**
- Success icon (✓) with green background
- Recognized sign in large text
- Confidence percentage (94%)
- Two action buttons:
  - "Speak This Word" (primary)
  - "Continue Listening" (secondary)

**Behavior:**
- Shows prediction with confidence
- Offers TTS option or continue recognition

---

### 5. SpeakingScreen

**Purpose:** Display audio playback UI with waveform animation

**Props:**
- `text: string | null` - Text being spoken
- `onComplete: () => void` - Called when audio finishes

**Visual Elements:**
- Recognized sign text in large blue font
- 12-bar animated waveform
- Audio progress bar (35% filled)
- "Audio playing..." status

**Animations:**
- Wave animation (0.6s cycle, staggered bars)
- Progress bar animation (3s)

**Behavior:**
- Shows waveform feedback during TTS
- Auto-completes and returns to listening

---

### 6. ErrorScreen

**Purpose:** Display error with troubleshooting options

**Props:**
- `errorMessage: string | null` - Error description
- `onRetry: () => void` - Called when user clicks retry

**Visual Elements:**
- Error icon (⚠) with red background
- Error message
- Troubleshooting list (4 items)
- Two action buttons:
  - "Retry" (primary)
  - "Reload Page" (secondary)

**Troubleshooting List:**
1. Check camera connection
2. Ensure permissions granted
3. Try refreshing
4. Check internet connection

**Behavior:**
- Clear error communication
- Multiple recovery options

---

## Dev Control Panel

### Purpose

Enables instant testing of all states without requiring actual camera input or ML model.

### Features

**Button Layout:**
```
🔧 DEV CONTROL PANEL    Current State: listening
┌────────────┬────────────┬────────────┬────────────┬────────────┬────────────┐
│ Permission │  Loading   │ Listening  │ Recognized │ Speaking   │   Error    │
│  Needed    │   Model    │            │            │            │            │
└────────────┴────────────┴────────────┴────────────┴────────────┴────────────┘
```

### Active State Indicator

The currently active state button is highlighted in orange with a glow effect.

### Usage

1. Click any button to instantly transition to that state
2. Special states pass simulated data:
   - "Sign Recognized": Sets `recognizedSign = "HELLO"`
   - "Speaking": Uses recognized sign
   - "Error": Sets default error message

### Fixed Positioning

- Located at bottom of screen (fixed height: 80px)
- Always visible above main content
- Horizontal scrollable on small screens

---

## State Management

### Hook: useState + useCallback

```typescript
const [currentState, setCurrentState] = useState<AppState>('permission_needed');
const [contextData, setContextData] = useState<AppContextData>({
  recognizedSign: null,
  errorMessage: null,
  audioWaveform: [],
});

const handleStateTransition = useCallback((transition: StateTransition) => {
  setCurrentState(transition.state);
  if (transition.data) {
    setContextData(prev => ({
      ...prev,
      recognizedSign: transition.data?.recognizedSign ?? prev.recognizedSign,
      errorMessage: transition.data?.errorMessage ?? prev.errorMessage,
      audioWaveform: transition.data?.audioWaveform ?? prev.audioWaveform,
    }));
  }
}, []);
```

### Data Flow

```
User Action
    ↓
handleStateTransition({ state, data })
    ↓
setCurrentState(state)
setContextData(newData)
    ↓
renderCurrentScreen()
    ↓
Component Re-render
```

---

## Type System

### AppState Union Type

Ensures only valid states exist. TypeScript enforces exhaustive checking:

```typescript
const renderCurrentScreen = () => {
  switch (currentState) {
    case 'permission_needed': return <PermissionNeededScreen />;
    case 'loading_model': return <LoadingModelScreen />;
    case 'listening': return <ListeningScreen />;
    case 'sign_recognized': return <SignRecognizedScreen />;
    case 'speaking': return <SpeakingScreen />;
    case 'error': return <ErrorScreen />;
    default:
      const _exhaustiveCheck: never = currentState;  // TS error if case missing
      return _exhaustiveCheck;
  }
};
```

### StateTransition Interface

```typescript
interface StateTransition {
  state: AppState;
  data?: {
    recognizedSign?: string;
    errorMessage?: string;
    audioWaveform?: number[];
  };
}
```

### AppContextData Interface

```typescript
interface AppContextData {
  recognizedSign: string | null;
  errorMessage: string | null;
  audioWaveform: number[];
}
```

---

## Styling System

### Inline Styles Object

All styles are defined in a single `styles` object for simplicity and component encapsulation:

```typescript
const styles: { [key: string]: React.CSSProperties } = {
  appContainer: { /* ... */ },
  screenContainer: { /* ... */ },
  // ... all other styles
};
```

### CSS Animations

Defined within `<style>` tags in specific components:

- **spin**: Spinner rotation (0.8s)
- **scan**: Scanning line animation (2s)
- **pulse**: Pulsing dot (1s)
- **wave**: Waveform bar animation (0.6s, staggered)
- **progress**: Audio progress bar (3s)

### Responsive Design

- Base font sizes: 12px - 64px
- Max content width: 600px
- Flexible button layouts
- Touch-friendly button sizes (min 44px height)

---

## Usage Examples

### Basic Integration

```typescript
import SignLanguageApp from './components/SignLanguageApp';

export default function App() {
  return <SignLanguageApp />;
}
```

### Programmatic State Changes

```typescript
// From parent component, use ref to control
const appRef = useRef<HTMLDivElement>(null);

// Trigger state change from outside
handleStateTransition({ 
  state: 'sign_recognized',
  data: { recognizedSign: 'THANK YOU' }
});
```

---

## Testing with Dev Panel

### Test Sequence

1. **Permission Flow**
   - Click "Permission Needed" → View camera permission request
   - Click "Loading Model" → View loading spinner
   - Click "Listening" → View camera feed

2. **Recognition Flow**
   - Click "Listening" → Main camera view
   - Click "Recognized" → View sign detection result
   - Click "Speaking" → View audio waveform

3. **Error Handling**
   - Click "Error" → View error screen
   - Click "Retry" → Returns to listening
   - Click "Reload Page" → Full page reload

### Visual Validation

✅ Each button state displays correct screen
✅ All animations play smoothly
✅ Text content is readable
✅ Buttons are interactive
✅ Responsive layout works

---

## Performance Considerations

### Optimizations

1. **useCallback Dependencies**: Action handlers memoized
2. **Conditional Rendering**: Only active screen renders
3. **Inline Styles**: No stylesheet parsing overhead
4. **Animation Efficiency**: CSS-based animations (GPU accelerated)

### Memory Usage

- Single state object per component
- No global state required
- Minimal re-renders via proper prop passing

---

## Future Enhancements

### Potential Features

1. **Real Camera Integration**
   - Replace camera placeholder with actual WebRTC stream
   - Permission handling

2. **Real ML Model**
   - TensorFlow.js or similar
   - Real gesture recognition

3. **Actual TTS**
   - Web Speech API integration
   - Replace waveform animation with real audio

4. **Error Analytics**
   - Error tracking and reporting
   - Automatic retry logic

5. **State Persistence**
   - Redux or Zustand integration
   - Session storage

6. **Accessibility**
   - ARIA labels for all elements
   - Keyboard navigation
   - High contrast mode

7. **Internationalization**
   - Multi-language support
   - RTL support

---

## Component File: SignLanguageApp.tsx

**Location:** `src/components/SignLanguageApp.tsx`

**Size:** ~1000 lines (complete implementation)

**Sections:**
1. Type Definitions (AppState, StateTransition, AppContextData)
2. Screen Components (6 components)
3. Dev Control Panel
4. Main App Component
5. Styles Object
6. Export

**All code is included - no truncation.**

---

## Build & Run

### Development

```bash
npm install
npm run dev
```

Runs TypeScript directly with ts-node, hot-reloads on file changes.

### Production Build

```bash
npm run build
npm start
```

Compiles TypeScript to JavaScript, runs compiled version.

---

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

---

## License

ISC

