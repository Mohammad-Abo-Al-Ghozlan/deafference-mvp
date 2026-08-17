/**
 * Stage 2: TensorFlow.js Quick Reference
 * 
 * This file serves as a quick lookup for common patterns and imports
 */

/* ============================================================ */
/* IMPORTS */
/* ============================================================ */

// Main model hook
import { useTensorFlowModel, useCanvasToVideoFrame } from '@/hooks/useTensorFlowModel';

// Type definitions
import type {
  PredictionEngine,
  PredictionResult,
  VideoFrame,
  UseTensorFlowModelReturn,
  ModelState,
} from '@/types/ml-model';

// Mock event types (for reference)
import type {
  MockEventType,
  SignRecognizedPayload,
  SignDiscardedPayload,
} from '@/types/mock-events';

/* ============================================================ */
/* COMMON PATTERNS */
/* ============================================================ */

// Pattern 1: Check if model is ready
// ─────────────────────────────────────
const { isModelReady, predictionEngine } = useTensorFlowModel();

if (isModelReady && predictionEngine) {
  // Safe to make predictions
}

// Pattern 2: Handle loading state
// ────────────────────────────────
const { isModelLoading, modelError } = useTensorFlowModel();

if (isModelLoading) {
  // Show loading indicator
}

if (modelError) {
  // Show error UI, provide retry button
  console.error('Model failed to load:', modelError.message);
}

// Pattern 3: Create VideoFrame from canvas
// ──────────────────────────────────────────
import { useRef } from 'react';

const canvasRef = useRef<HTMLCanvasElement>(null);

// Option A: Manual frame creation
const createVideoFrame = (): VideoFrame => {
  const canvas = canvasRef.current!;
  const ctx = canvas.getContext('2d')!;
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  
  return {
    data: imageData.data,
    width: canvas.width,
    height: canvas.height,
  };
};

// Option B: Use helper hook
const frame = useCanvasToVideoFrame(canvasRef);

// Pattern 4: Make a prediction
// ─────────────────────────────
const makePrediction = async () => {
  if (!predictionEngine || !isModelReady) return;

  const frame: VideoFrame = createVideoFrame();
  const result = await predictionEngine.predict(frame);

  if (result.type === 'recognized') {
    console.log(`Sign: ${result.label} (${(result.confidence * 100).toFixed(1)}%)`);
  } else {
    console.log(`Discarded: ${result.reason}`);
  }
};

// Pattern 5: Type-safe prediction handling
// ─────────────────────────────────────────
const handlePredictionResult = (result: PredictionResult) => {
  switch (result.type) {
    case 'recognized': {
      const label: string = result.label;
      const confidence: number = result.confidence;
      const timestamp: number = result.timestamp;
      // ✅ All properties are guaranteed to exist
      break;
    }
    case 'discarded': {
      const reason: 'low_confidence' | 'gesture_incomplete' | 'no_hand_detected' | 'multiple_hands' = result.reason;
      const confidence: number = result.confidence;
      const timestamp: number = result.timestamp;
      // ✅ All properties are guaranteed to exist
      break;
    }
  }
};

// Pattern 6: Integration with state machine
// ──────────────────────────────────────────
// Automatic! The EnhancedSignLanguageStateMachine already handles:
//   1. Initiating model load when entering 'loading_model' state
//   2. Transitioning to 'listening' when isModelReady = true
//   3. Showing error UI if modelError occurs
//   4. Cleanup on unmount

// Pattern 7: Continuous frame processing
// ───────────────────────────────────────
const startContinuousPrediction = () => {
  const { isModelReady, predictionEngine } = useTensorFlowModel();

  useEffect(() => {
    if (!isModelReady || !predictionEngine) return;

    const processFrame = async () => {
      const frame = createVideoFrame();
      const result = await predictionEngine.predict(frame);
      handlePredictionResult(result);

      // Request next frame
      requestAnimationFrame(processFrame);
    };

    processFrame();
  }, [isModelReady, predictionEngine]);
};

// Pattern 8: Error recovery
// ──────────────────────────
const handleModelError = (error: Error | null) => {
  if (error) {
    console.error('[ML Model] Error:', error.message);
    // Options:
    // 1. Show error UI
    // 2. Offer retry button (restart state machine)
    // 3. Log to analytics
  }
};

/* ============================================================ */
/* TYPE REFERENCE */
/* ============================================================ */

/**
 * PredictionResult Union Type
 */
// Recognized Sign
type RecognizedPrediction = {
  type: 'recognized';
  label: string;                              // e.g., "Hello", "Thank you"
  confidence: number;                         // 0.0 - 1.0
  timestamp: number;                          // milliseconds since epoch
};

// Discarded Gesture
type DiscardedPrediction = {
  type: 'discarded';
  reason: 'low_confidence' | 'gesture_incomplete' | 'no_hand_detected' | 'multiple_hands';
  confidence: number;                         // 0.0 - 1.0
  timestamp: number;                          // milliseconds since epoch
};

/**
 * VideoFrame Format
 */
type VideoFrameType = {
  data: ArrayLike | undefined;                // Pixel data from canvas
  width: number;                              // Frame width in pixels
  height: number;                             // Frame height in pixels
};

/**
 * Model State
 */
type ModelStateType = {
  isModelLoading: boolean;                    // true while initializing
  isModelReady: boolean;                      // true when ready for predictions
  modelError: Error | null;                   // null if no error
};

/* ============================================================ */
/* STATE MACHINE INTEGRATION CHECKLIST */
/* ============================================================ */

// ✅ Model initialization starts when state = 'loading_model'
// ✅ Progress bar shows real TensorFlow initialization
// ✅ Auto-transition to 'listening' when isModelReady = true
// ✅ Error UI shown if modelError !== null
// ✅ Retry button returns to 'permission_needed' for re-initialization
// ✅ Resources cleaned up on unmount
// ✅ Type-safe prediction engine provided in 'listening' state

/* ============================================================ */
/* MOCK VS REAL MODEL COMPARISON */
/* ============================================================ */

/**
 * MockPredictionEngine (Current - Stage 2)
 * ────────────────────────────────────────
 * - Simulates inference latency (150-300ms)
 * - Alternates predictions and discards
 * - Returns mock ASL vocabulary
 * - No external file loading
 * - Perfect for testing state machine and UI
 * 
 * Usage:
 *   npm install @tensorflow/tfjs
 *   useTensorFlowModel() initializes automatically
 */

/**
 * Real Model (Coming - Stage 3)
 * ─────────────────────────────
 * - tf.loadLayersModel('model.json')
 * - Real computer vision inference
 * - Sign detection from video stream
 * - Requires trained TensorFlow.js compatible model
 * 
 * Migration:
 *   Replace MockPredictionEngine class with RealPredictionEngine
 *   Update model loading logic
 *   Add preprocessing pipeline
 */

/* ============================================================ */
/* DEBUGGING TIPS */
/* ============================================================ */

// Tip 1: Verify TensorFlow is initialized
console.log('TF ready:', typeof tf !== 'undefined');

// Tip 2: Check model lifecycle
const logModelState = () => {
  const { isModelLoading, isModelReady, modelError, predictionEngine } = useTensorFlowModel();
  console.table({
    isModelLoading,
    isModelReady,
    modelError: modelError?.message,
    predictionEngineExists: !!predictionEngine,
  });
};

// Tip 3: Monitor predictions
const logPrediction = (result: PredictionResult) => {
  const timestamp = new Date(result.timestamp).toISOString();
  if (result.type === 'recognized') {
    console.log(`[${timestamp}] ✓ ${result.label} (${(result.confidence * 100).toFixed(1)}%)`);
  } else {
    console.log(`[${timestamp}] ✗ ${result.reason}`);
  }
};

// Tip 4: Check canvas dimensions
const validateCanvasDimensions = (video: HTMLVideoElement, canvas: HTMLCanvasElement) => {
  console.assert(canvas.width === video.videoWidth, 'Canvas width mismatch');
  console.assert(canvas.height === video.videoHeight, 'Canvas height mismatch');
};

/* ============================================================ */
/* PERFORMANCE NOTES */
/* ============================================================ */

// Frame Processing Time: ~150-300ms per prediction (mock)
// Memory Usage: ~50-100MB for TensorFlow.js + model
// GPU Acceleration: Automatic via WebGL if available
// Browser Support: All modern browsers (Chrome, Firefox, Safari, Edge)

// Optimization tips for Stage 3:
// - Batch predictions (process multiple frames before inference)
// - Use OffscreenCanvas for worker threads
// - Implement frame skipping (process every Nth frame)
// - Pre-allocate tensors when possible

export {};
