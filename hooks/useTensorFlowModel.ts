'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import * as tf from '@tensorflow/tfjs';
import {
  PredictionEngine,
  PredictionResult,
  VideoFrame,
  UseTensorFlowModelReturn,
} from '@/types/ml-model';
import { MOCK_ASL_VOCABULARY, DISCARD_REASONS } from '@/types/mock-events';

/**
 * Mock prediction engine that simulates TF.js model inference
 * Implements the PredictionEngine interface without requiring a real model file
 *
 * @internal This is a stub implementation for Stage 2
 */
class MockPredictionEngine implements PredictionEngine {
  private lastWasPrediction: boolean = false;

  /**
   * Simulate model inference with realistic delay and alternating prediction/discard pattern
   * Mimics the Stage 1 mock event generator behavior but integrated with TensorFlow lifecycle
   */
  async predict(frame: VideoFrame): Promise<PredictionResult> {
    // Simulate inference latency (150-300ms typical for sign detection)
    const latency = Math.random() * 150 + 150;
    await new Promise((resolve) => setTimeout(resolve, latency));

    // Validate frame input
    if (!frame || frame.width === 0 || frame.height === 0) {
      return {
        type: 'discarded',
        reason: 'no_hand_detected',
        confidence: Math.random() * 0.3,
        timestamp: Date.now(),
      };
    }

    // Alternate between predictions and discards for realistic testing
    const shouldPredict = !this.lastWasPrediction;
    this.lastWasPrediction = !this.lastWasPrediction;

    const timestamp = Date.now();

    if (shouldPredict) {
      // Generate a positive prediction
      const randomLabel =
        MOCK_ASL_VOCABULARY[Math.floor(Math.random() * MOCK_ASL_VOCABULARY.length)];
      const confidence = Math.random() * (0.99 - 0.75) + 0.75; // 0.75-0.99 range

      return {
        type: 'recognized',
        label: randomLabel,
        confidence,
        timestamp,
      };
    } else {
      // Generate a discard result
      const randomReason = DISCARD_REASONS[Math.floor(Math.random() * DISCARD_REASONS.length)];
      const confidence = Math.random() * (0.5 - 0.15) + 0.15; // 0.15-0.5 range

      return {
        type: 'discarded',
        reason: randomReason,
        confidence,
        timestamp,
      };
    }
  }

  /**
   * Cleanup resources (no-op for mock engine)
   */
  dispose(): void {
    // Mock engine has no resources to dispose
  }
}

/**
 * Custom React hook for TensorFlow.js model initialization and lifecycle management
 *
 * Manages:
 * - TensorFlow.js initialization via tf.ready()
 * - Model loading state (loading, ready, error)
 * - Prediction engine creation and disposal
 * - Proper TypeScript typing for type-safe inference
 *
 * @returns Object containing model state and prediction engine
 *
 * @example
 * ```tsx
 * const { isModelLoading, isModelReady, modelError, predictionEngine } = useTensorFlowModel();
 *
 * useEffect(() => {
 *   if (isModelReady && predictionEngine) {
 *     const frame: VideoFrame = { data: canvasData, width: 640, height: 480 };
 *     predictionEngine.predict(frame).then(result => {
 *       if (result.type === 'recognized') {
 *         console.log(`Recognized: ${result.label} (${result.confidence})`);
 *       }
 *     });
 *   }
 * }, [isModelReady, predictionEngine]);
 * ```
 */
/** Maximum time to wait for TF.js + the model to become ready before treating it as a failure */
const MODEL_LOAD_TIMEOUT_MS = 15000;

/**
 * Rejects with a timeout error if `promise` doesn't settle within `timeoutMs`.
 * The underlying timer is always cleared so it can't fire after the race is decided.
 */
const withTimeout = <T,>(promise: Promise<T>, timeoutMs: number): Promise<T> => {
  let timeoutId: ReturnType<typeof setTimeout>;

  const timeoutPromise = new Promise<never>((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      reject(new Error(`Model loading timed out after ${timeoutMs / 1000}s. Please check your network connection.`));
    }, timeoutMs);
  });

  return Promise.race([promise, timeoutPromise]).finally(() => {
    clearTimeout(timeoutId);
  });
};

export const useTensorFlowModel = (): UseTensorFlowModelReturn => {
  const [isModelLoading, setIsModelLoading] = useState<boolean>(true);
  const [isModelReady, setIsModelReady] = useState<boolean>(false);
  const [modelError, setModelError] = useState<Error | null>(null);
  const [predictionEngine, setPredictionEngine] = useState<PredictionEngine | null>(null);

  // Reference to prevent cleanup on model ready (persist across re-renders)
  const engineRef = useRef<PredictionEngine | null>(null);

  // Bumped on every load attempt so a stale (e.g. superseded-by-retry) attempt
  // can detect it's no longer current and skip updating state.
  const attemptIdRef = useRef<number>(0);
  const isInitializingRef = useRef<boolean>(false);

  const initializeModel = useCallback(async (): Promise<void> => {
    if (isInitializingRef.current) {
      return;
    }
    isInitializingRef.current = true;

    const attemptId = ++attemptIdRef.current;

    try {
      setIsModelLoading(true);
      setModelError(null);

      // Wait for TensorFlow.js to be ready and backend initialized, bounded by a
      // timeout so a stalled network/CORS/OOM failure doesn't hang forever.
      // This ensures WebGL/WebAssembly backend is available if supported.
      await withTimeout(tf.ready(), MODEL_LOAD_TIMEOUT_MS);

      if (attemptId !== attemptIdRef.current) {
        // A newer attempt (retry) has started; discard this stale result.
        return;
      }

      // Stage 2: Create mock prediction engine
      // In Stage 3, this will be replaced with: tf.loadLayersModel('path/to/model.json')
      const engine = new MockPredictionEngine();
      engineRef.current = engine;
      setPredictionEngine(engine);

      setIsModelReady(true);
      setIsModelLoading(false);
    } catch (error) {
      if (attemptId !== attemptIdRef.current) {
        // A newer attempt (retry) has started; discard this stale failure.
        return;
      }

      const errorObj = error instanceof Error ? error : new Error('Unknown model initialization error');
      setModelError(errorObj);
      setIsModelLoading(false);
      setIsModelReady(false);

      // Log error for debugging
      console.error('[TensorFlow Model] Initialization failed:', errorObj);
    } finally {
      isInitializingRef.current = false;
    }
  }, []);

  const retry = useCallback((): void => {
    setModelError(null);
    setPredictionEngine(null);
    setIsModelReady(false);
    initializeModel();
  }, [initializeModel]);

  /**
   * Initialize TensorFlow.js and create prediction engine
   * Runs once on component mount
   */
  useEffect(() => {
    initializeModel();

    // Cleanup function: dispose prediction engine resources on unmount
    return () => {
      if (engineRef.current) {
        engineRef.current.dispose();
        engineRef.current = null;
      }
      // Dispose TensorFlow.js resources
      // Note: Be cautious with tf.disposeVariables() in production
      // as it may dispose shared tensors
    };
  }, [initializeModel]);

  return {
    isModelLoading,
    isModelReady,
    modelError,
    hasError: modelError !== null,
    errorMessage: modelError?.message ?? null,
    predictionEngine,
    retry,
  };
};

/**
 * Helper hook to convert canvas element to VideoFrame format
 * Useful for processing HTMLCanvasElement from video stream
 *
 * @param canvasRef - Reference to HTMLCanvasElement
 * @returns VideoFrame object suitable for prediction engine
 */
export const useCanvasToVideoFrame = (
  canvasRef: React.RefObject<HTMLCanvasElement | null>
): VideoFrame => {
  const [frame, setFrame] = useState<VideoFrame>({
    data: undefined,
    width: 0,
    height: 0,
  });

  useEffect(() => {
    if (!canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');

    if (!ctx) {
      console.error('[Video Frame] Failed to get canvas context');
      return;
    }

    try {
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      setFrame({
        data: imageData.data,
        width: canvas.width,
        height: canvas.height,
      });
    } catch (error) {
      console.error('[Video Frame] Failed to extract frame:', error);
    }
  }, [canvasRef]);

  return frame;
};
