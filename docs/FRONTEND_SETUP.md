# Frontend Setup & Integration Guide

## Quick Start

### 1. Install Dependencies (Updated)

The project now includes React and React DOM:

```bash
npm install
```

This will install:
- React 18.2.0
- React DOM 18.2.0
- TypeScript type definitions for React
- All backend dependencies

### 2. Review Component Structure

The frontend component is a complete, self-contained React component:

```
src/
├── components/
│   └── SignLanguageApp.tsx        # Main State Machine (1000+ lines, complete)
├── App.tsx                        # React app wrapper
└── index.ts                       # Backend server (can be kept separate)
```

### 3. Component Features

**SignLanguageApp.tsx** includes:

✅ **6 State Screens**
- PermissionNeededScreen
- LoadingModelScreen
- ListeningScreen
- SignRecognizedScreen
- SpeakingScreen
- ErrorScreen

✅ **State Machine Management**
- Type-safe state transitions
- Context data management
- Exhaustive type checking

✅ **Dev Control Panel**
- Instant state switching
- No ML model required
- Perfect for testing

✅ **Comprehensive Styling**
- Inline CSS-in-JS
- CSS animations
- Responsive design

✅ **No External Dependencies**
- Only React required
- Self-contained styles
- Animations via pure CSS

### 4. Usage in Your App

**Option A: Full App (Recommended)**

```tsx
import React from 'react';
import SignLanguageApp from './components/SignLanguageApp';

function App() {
  return <SignLanguageApp />;
}

export default App;
```

**Option B: With Custom Styling**

```tsx
import React from 'react';
import SignLanguageApp from './components/SignLanguageApp';

function App() {
  return (
    <div style={{ 
      width: '100%', 
      height: '100vh',
      fontFamily: 'system-ui, -apple-system, sans-serif'
    }}>
      <SignLanguageApp />
    </div>
  );
}

export default App;
```

## State Machine Overview

### All 6 States

| State | Purpose | Key Components |
|-------|---------|-----------------|
| `permission_needed` | Request camera permission | Icon, features list, CTA button |
| `loading_model` | Initialize ML model | Spinner, progress steps |
| `listening` | Camera feed + recognition | Camera placeholder, scanning overlay |
| `sign_recognized` | Show detected sign | Success icon, sign text, confidence |
| `speaking` | Text-to-speech playback | Waveform animation, progress bar |
| `error` | Error handling | Error icon, message, troubleshooting |

### Type Definitions

All types are built-in to the component:

```typescript
type AppState = 
  | 'permission_needed' 
  | 'loading_model' 
  | 'listening' 
  | 'sign_recognized' 
  | 'speaking' 
  | 'error';
```

## Dev Control Panel

The component includes a **fixed bottom panel** with debug buttons to test every state:

```
🔧 DEV CONTROL PANEL    Current State: listening
┌─────────┬─────────┬─────────┬─────────┬─────────┬─────────┐
│ Perm... │ Loading │Listening│Recognized│Speaking│ Error  │
└─────────┴─────────┴─────────┴─────────┴─────────┴─────────┘
```

**Features:**
- ✅ Instant state switching
- ✅ Active state highlighted in orange
- ✅ Works without ML model
- ✅ Fixed position (always visible)
- ✅ Auto-pass sample data (e.g., "HELLO" for recognized sign)

## Code Organization

### Components (All in One File)

```typescript
SignLanguageApp.tsx
├── Type Definitions
│   ├── type AppState
│   ├── interface StateTransition
│   └── interface AppContextData
│
├── 6 Screen Components
│   ├── PermissionNeededScreen
│   ├── LoadingModelScreen
│   ├── ListeningScreen
│   ├── SignRecognizedScreen
│   ├── SpeakingScreen
│   └── ErrorScreen
│
├── Dev Control Panel
│   └── DevControlPanel component
│
├── Main App Component
│   └── SignLanguageApp (state manager & router)
│
└── Styles Object
    └── Complete inline CSS-in-JS
```

### State Management

```typescript
// Main component uses React hooks
const [currentState, setCurrentState] = useState<AppState>('permission_needed');
const [contextData, setContextData] = useState<AppContextData>({
  recognizedSign: null,
  errorMessage: null,
  audioWaveform: [],
});

// Transition handler
const handleStateTransition = useCallback((transition: StateTransition) => {
  setCurrentState(transition.state);
  if (transition.data) {
    setContextData(prev => ({ ...prev, ...transition.data }));
  }
}, []);
```

## Testing the States

### Manual Testing with Dev Panel

1. **Permission State**
   ```
   Click: "Permission Needed"
   See: Camera permission request screen
   ```

2. **Loading State**
   ```
   Click: "Loading Model"
   See: Spinner + loading steps
   ```

3. **Listening State**
   ```
   Click: "Listening"
   See: Camera placeholder with scanning animation
   ```

4. **Recognition State**
   ```
   Click: "Sign Recognized"
   See: Success message + "HELLO" text
   ```

5. **Speaking State**
   ```
   Click: "Speaking"
   See: Waveform animation + progress bar
   ```

6. **Error State**
   ```
   Click: "Error"
   See: Error message + troubleshooting steps
   ```

### Automated Testing (with Jest - Future)

```typescript
describe('SignLanguageApp', () => {
  test('renders permission screen on mount', () => {
    render(<SignLanguageApp />);
    expect(screen.getByText(/Grant Camera Permission/i)).toBeInTheDocument();
  });

  test('transitions to loading when permission granted', () => {
    const { getByText } = render(<SignLanguageApp />);
    fireEvent.click(getByText(/Grant Camera Permission/i));
    expect(screen.getByText(/Initializing AI Model/i)).toBeInTheDocument();
  });

  // ... more tests
});
```

## Styling & Animations

### CSS Animations Included

1. **Spinner** - Continuous rotation (0.8s)
2. **Scan Line** - Vertical motion (2s)
3. **Pulse Dot** - Size + opacity (1s)
4. **Waveform** - Height variation (0.6s, staggered)
5. **Progress Bar** - Width animation (3s)

All animations use CSS for GPU acceleration and smooth 60fps performance.

### Customization

Change any style by modifying the `styles` object:

```typescript
const styles: { [key: string]: React.CSSProperties } = {
  screenTitle: {
    fontSize: '28px',  // Modify here
    fontWeight: 600,
    color: '#1a1a1a',
  },
  // ... more styles
};
```

## Integration with Backend

The frontend (React) and backend (Express/Node.js) run separately:

### Backend (Port 3000)

```bash
npm run dev    # Runs Express server on localhost:3000
```

**Endpoints:**
- `POST /api/users/camera-permission` - Save permission
- `GET /api/users/:userId/camera-permission` - Get permission
- `GET /health` - Health check

### Frontend (Port 3000 or 3001)

```bash
# Run React app (requires create-react-app or Vite setup)
# For now, included as component to be used with React
```

### Connecting Them

Once you have a React dev server running (e.g., with `create-react-app` or `Vite`):

```typescript
// In your React app
const savePermissionStatus = async (userId: string, status: 'granted' | 'denied') => {
  try {
    const response = await fetch('http://localhost:3000/api/users/camera-permission', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        userId,
        status,
        updatedAt: new Date().toISOString(),
      }),
    });
    const data = await response.json();
    console.log('Permission saved:', data);
  } catch (error) {
    console.error('Error saving permission:', error);
  }
};
```

## File Locations

```
deafference-sign-ai-mvp-1/
├── src/
│   ├── components/
│   │   └── SignLanguageApp.tsx          ✅ NEW (1000+ lines, complete)
│   ├── App.tsx                          ✅ NEW (React wrapper)
│   ├── controllers/
│   │   └── CameraPermissionController.ts
│   ├── services/
│   │   └── CameraPermissionService.ts
│   ├── routes/
│   │   └── userRoutes.ts
│   ├── types/
│   │   ├── permissions.ts
│   │   └── validation.ts
│   └── index.ts                         (Backend entry)
│
├── FRONTEND_ARCHITECTURE.md             ✅ NEW (Detailed docs)
├── README.md                            (Existing backend setup)
├── package.json                         ✅ UPDATED (React added)
└── ... other files ...
```

## Key Files to Review

1. **SignLanguageApp.tsx** (1000+ lines)
   - Main component with all state logic
   - Complete implementation
   - No truncation

2. **App.tsx** (wrapper)
   - Simple React app wrapper
   - Ready to use

3. **FRONTEND_ARCHITECTURE.md**
   - Detailed architecture explanation
   - State diagrams
   - All 6 screen specifications

## Performance Notes

✅ **Optimized:**
- Memoized state handlers (useCallback)
- Efficient re-renders
- CSS animations (GPU accelerated)
- No external UI libraries

⚠️ **Consider adding:**
- React.memo for screen components
- useReducer for complex logic (future)
- Error boundary for error handling
- Lazy loading for large components

## Browser Compatibility

- ✅ Chrome 90+
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Edge 90+

## Next Steps

1. ✅ Review SignLanguageApp.tsx component
2. ✅ Test with Dev Control Panel
3. ✅ Customize styles if needed
4. ✅ Integrate real camera API
5. ✅ Connect to backend API
6. ✅ Add real ML model
7. ✅ Add real TTS

## Support

Refer to:
- `FRONTEND_ARCHITECTURE.md` - Deep dive on architecture
- `SignLanguageApp.tsx` - Complete implementation
- React documentation: https://react.dev

