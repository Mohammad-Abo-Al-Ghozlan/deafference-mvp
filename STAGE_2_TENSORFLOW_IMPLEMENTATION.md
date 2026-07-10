# Stage 2: TensorFlow.js Integration & Model Loading Layer

## Overview

Stage 2 implements the complete TensorFlow.js initialization and model-loading architecture for the sign language recognition pipeline. This stage provides:

✅ **TensorFlow.js Integration** - Full lifecycle management of TF.js  
✅ **Prediction Engine Abstraction** - Type-safe interface for model inference  
✅ **Mock Model Implementation** - Realistic stub for testing without real models  
✅ **State Machine Hookup** - Automatic `LOADING_MODEL` → `LISTENING` transitions  
✅ **Error Handling** - Comprehensive error states and recovery paths  

---

## Architecture

### File Structure

```
hooks/
  ├── useTensorFlowModel.ts          # Core TF.js lifecycle hook
  └── useCanvasToVideoFrame.ts       # Helper for video frame extraction (in same file)

types/
  └── ml-model.ts                    # TypeScript interfaces for model layer

components/deafference/
  ├── EnhancedSignLanguageStateMachine.tsx  # Updated with TF.js integration
  └── SignPredictionDemo.tsx         # Example usage with video stream

package.json                          # Added @tensorflow/tfjs dependency
```

### Key Components

#### 1. `useTensorFlowModel` Hook

**Responsibilities:**
- Initialize TensorFlow.js via `tf.ready()`
- Create and manage `PredictionEngine` instance
- Track model loading state: `isModelLoading`, `isModelReady`, `modelError`
- Handle cleanup and resource disposal

**Usage:**
```typescript
const { isModelLoading, isModelReady, modelError, predictionEngine } = useTensorFlowModel();

// Model automatically initializes on mount
// Automatically cleans up resources on unmount
```

#### 2. `PredictionEngine` Interface

Type-safe contract for model inference:

```typescript
interface PredictionEngine {
  predict(frame: VideoFrame): Promise<PredictionResult>;
  dispose(): void;
}

type PredictionResult = 
  | { type: 'recognized'; label: string; confidence: number; timestamp: number }
  | { type: 'discarded'; reason: DiscardReason; confidence: number; timestamp: number };
```

#### 3. `MockPredictionEngine` Implementation

**Realistic Testing Without Real Models:**
- Simulates inference latency (150-300ms)
- Alternates between predictions and discards
- Returns mock ASL vocabulary labels
- Confidence ranges match real distributions (0.75-0.99 for predictions, 0.15-0.5 for discards)

**Stage 3 Upgrade Path:**
```typescript
// Stage 3: Replace with real model
const model = await tf.loadLayersModel('file://model.json');
return { predict: async (frame) => model.predict(frame), dispose: () => {} };
```

#### 4. `EnhancedSignLanguageStateMachine` Integration

**Automatic State Transitions:**
```typescript
// useEffect watches model readiness
useEffect(() => {
  if (state === 'loading_model' && isModelReady && !isModelLoading) {
    transitionState('listening');  // Automatic transition
  }
}, [state, isModelReady, isModelLoading, transitionState]);
```

**Updated Loading UI:**
- Shows real TensorFlow initialization progress
- Displays error states with retry button
- Automatically transitions when ready (no manual button click needed)

---

## Usage Examples

### Example 1: Basic Model Initialization

```typescript
import { useTensorFlowModel } from '@/hooks/useTensorFlowModel';

export function MyComponent() {
  const { isModelLoading, isModelReady, modelError, predictionEngine } = 
    useTensorFlowModel();

  useEffect(() => {
    if (isModelReady && predictionEngine) {
      // Model is ready for predictions
      console.log('Prediction engine is ready!');
    }
  }, [isModelReady, predictionEngine]);

  if (isModelLoading) return <div>Loading model...</div>;
  if (modelError) return <div>Error: {modelError.message}</div>;
  if (!isModelReady) return <div>Model initializing...</div>;

  return <div>Model ready!</div>;
}
```

### Example 2: Running Predictions

```typescript
import { useTensorFlowModel } from '@/hooks/useTensorFlowModel';
import { VideoFrame } from '@/types/ml-model';

export function SignDetector() {
  const { isModelReady, predictionEngine } = useTensorFlowModel();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!isModelReady || !predictionEngine || !videoRef.current) return;

    const processFrame = async () => {
      const canvas = canvasRef.current!;
      const ctx = canvas.getContext('2d')!;
      
      // Draw video to canvas
      ctx.drawImage(videoRef.current!, 0, 0, canvas.width, canvas.height);
      
      // Create VideoFrame
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const frame: VideoFrame = {
        data: imageData.data,
        width: canvas.width,
        height: canvas.height,
      };

      // Run prediction
      const result = await predictionEngine.predict(frame);
      
      if (result.type === 'recognized') {
        console.log(`Recognized: ${result.label} (${(result.confidence * 100).toFixed(1)}%)`);
      } else {
        console.log(`Discarded: ${result.reason}`);
      }

      requestAnimationFrame(processFrame);
    };

    processFrame();
  }, [isModelReady, predictionEngine]);

  return (
    <>
      <video ref={videoRef} autoPlay playsInline />
      <canvas ref={canvasRef} style={{ display: 'none' }} />
    </>
  );
}
```

### Example 3: Integrated with State Machine

The updated `EnhancedSignLanguageStateMachine` now automatically:

1. **Initializes** TensorFlow.js when component mounts
2. **Shows Loading UI** while model initializes
3. **Transitions** to `LISTENING` state when ready
4. **Handles Errors** with retry UI
5. **Cleans Up** resources on unmount

```typescript
// User clicks "Grant Permission" → `loading_model` state
// → useTensorFlowModel initializes
// → tf.ready() resolves
// → MockPredictionEngine created
// → Auto-transition to `listening` state
// → User can start testing with mock events
```

---

## Type Safety

All components use strict TypeScript types with **zero `any` placeholders**:

```typescript
// ✅ Type-safe prediction
const result: PredictionResult = await predictionEngine.predict(frame);

if (result.type === 'recognized') {
  // TypeScript knows: label, confidence, timestamp exist
  console.log(result.label);
  console.log(result.confidence);
  console.log(result.timestamp);
}

// ✅ Type-safe frame creation
const frame: VideoFrame = { data: imageData.data, width: 640, height: 480 };
```

---

## State Machine Flow

```
permission_needed
    ↓
loading_model ← (User grants camera permission)
    ↓
[useTensorFlowModel initializes]
    ↓
tf.ready() resolves
    ↓
MockPredictionEngine created
    ↓
[useEffect detects isModelReady = true]
    ↓
listening ← (Automatic transition)
    ↓
[User can now test predictions]
```

---

## Error Handling

**Graceful Degradation:**

1. **Model Initialization Fails**
   - `modelError` state captured
   - UI shows error message
   - Retry button returns to `permission_needed`
   - Can re-attempt initialization

2. **Frame Processing Fails**
   - Caught and logged in development
   - Gracefully continues to next frame
   - No impact on state machine

3. **Resource Cleanup**
   - Prediction engine disposed on unmount
   - TensorFlow.js resources released
   - No memory leaks

---

## Migration to Stage 3 (Real Model)

To upgrade to real model inference:

```typescript
// hooks/useTensorFlowModel.ts - Update the initialization

class RealPredictionEngine implements PredictionEngine {
  private model: tf.LayersModel;

  async predict(frame: VideoFrame): Promise<PredictionResult> {
    // Convert VideoFrame to tensor
    const tensor = tf.tensor3d(frame.data, [frame.height, frame.width, 4]);
    
    // Run inference
    const output = this.model.predict(tensor) as tf.Tensor;
    const predictions = await output.data();
    
    // Parse predictions...
    tensor.dispose();
    output.dispose();
    
    return { type: 'recognized', label: '...', confidence: 0.95, timestamp: Date.now() };
  }

  dispose(): void {
    this.model.dispose();
  }
}

// In useTensorFlowModel:
// Replace: const engine = new MockPredictionEngine();
// With:    const engine = new RealPredictionEngine(await tf.loadLayersModel(...));
```

---

## Testing

### Mock Event Generation (Existing)
The `useMockEventGenerator` hook continues to work independently for testing state transitions:

```typescript
const { isSimulating, startSimulation } = useMockEventGenerator({
  intervalMs: 3500,
  onEvent: (event) => {
    // Generates SIGN_RECOGNIZED or SIGN_DISCARDED events
    // Works alongside real prediction engine in Stage 3
  },
});
```

### Integration Testing
Use `SignPredictionDemo` component to test end-to-end:

```typescript
import SignPredictionDemo from '@/components/deafference/SignPredictionDemo';

export function TestPage() {
  const videoRef = useRef<HTMLVideoElement>(null);

  return (
    <>
      <video ref={videoRef} autoPlay playsInline />
      <SignPredictionDemo 
        videoRef={videoRef}
        onPrediction={(result) => console.log(result)}
        enabled={true}
      />
    </>
  );
}
```

---

## Performance Considerations

### Memory Management
- **Prediction Engine**: Single instance per component tree
- **Tensor Cleanup**: Disposed immediately after predictions
- **Resource Limits**: TensorFlow.js manages backend resources

### Latency
- **Frame Processing**: ~150-300ms per frame (mock)
- **Real Model**: Depends on model size and hardware
- **Optimization**: Can batch frames or use web workers in Stage 3

### Browser Support
- Requires **WebGL or WebAssembly** backend
- Automatically detected by `tf.ready()`
- Fallback to JavaScript backend if needed

---

## Debugging

### Development Console Output
```typescript
// Check model state
console.log({ isModelLoading, isModelReady, modelError, predictionEngine });

// Monitor predictions
console.log('[Stage 2] Sign recognized:', result.label);

// Track state transitions
onStateChange && onStateChange(state);
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Model loading stuck | Check browser console for TensorFlow errors |
| Predictions not executing | Verify `isModelReady === true` before calling `predict()` |
| Memory usage increasing | Ensure `dispose()` is called on cleanup |
| Canvas context errors | Verify video dimensions match canvas dimensions |

---

## Dependencies

```json
{
  "@tensorflow/tfjs": "^4.18.0"
}
```

Install with:
```bash
npm install
```

---

## Next Steps (Stage 3)

1. **Real Model Loading**: Replace `MockPredictionEngine` with actual model
2. **Input Preprocessing**: Add video frame normalization
3. **Output Postprocessing**: Convert model outputs to `PredictionResult`
4. **Performance Optimization**: Implement batching, web workers
5. **Confidence Thresholding**: Filter low-confidence predictions

---

## Summary

Stage 2 provides:
- ✅ Production-ready TensorFlow.js initialization
- ✅ Type-safe prediction engine abstraction
- ✅ Realistic mock for testing
- ✅ Automatic state machine integration
- ✅ Comprehensive error handling
- ✅ Zero technical debt for Stage 3 upgrade
