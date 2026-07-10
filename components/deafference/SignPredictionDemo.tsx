'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useTensorFlowModel, useCanvasToVideoFrame } from '@/hooks/useTensorFlowModel';
import { VideoFrame, PredictionResult } from '@/types/ml-model';

interface SignPredictionDemoProps {
  videoRef?: React.RefObject<HTMLVideoElement>;
  onPrediction?: (result: PredictionResult) => void;
  enabled?: boolean;
}

/**
 * Demo component showing Stage 2 integration of TensorFlow.js prediction engine
 * 
 * This component demonstrates:
 * - Initializing the prediction engine via useTensorFlowModel
 * - Processing video frames into VideoFrame format
 * - Executing predictions with type safety
 * - Handling recognized signs vs discarded gestures
 * 
 * @example
 * ```tsx
 * const videoRef = useRef<HTMLVideoElement>(null);
 * return (
 *   <>
 *     <video ref={videoRef} />
 *     <SignPredictionDemo 
 *       videoRef={videoRef}
 *       onPrediction={(result) => {
 *         if (result.type === 'recognized') {
 *           console.log(`Sign: ${result.label}`);
 *         }
 *       }}
 *       enabled={true}
 *     />
 *   </>
 * );
 * ```
 */
export default function SignPredictionDemo({
  videoRef,
  onPrediction,
  enabled = true,
}: SignPredictionDemoProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationFrameRef = useRef<number | undefined>(undefined);
  
  // Initialize TensorFlow model and prediction engine
  const { isModelLoading, isModelReady, modelError, predictionEngine } =
    useTensorFlowModel();

  // Convert canvas to VideoFrame format
  const frame = useCanvasToVideoFrame(canvasRef);

  /**
   * Extract frame from video element and run prediction
   * Runs continuously while enabled and model is ready
   */
  const processVideoFrame = useCallback(async (): Promise<void> => {
    if (!videoRef?.current || !canvasRef.current || !enabled || !isModelReady || !predictionEngine) {
      return;
    }

    try {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      const ctx = canvas.getContext('2d');

      if (!ctx) {
        console.error('[Prediction] Failed to get canvas context');
        return;
      }

      // Set canvas to video dimensions
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;

      // Draw current video frame to canvas
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      // Create VideoFrame from canvas
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const videoFrame: VideoFrame = {
        data: imageData.data,
        width: canvas.width,
        height: canvas.height,
      };

      // Execute prediction
      const result = await predictionEngine.predict(videoFrame);

      // Handle prediction result
      if (result.type === 'recognized') {
        console.log(`[Stage 2] Sign recognized: ${result.label} (confidence: ${(result.confidence * 100).toFixed(1)}%)`);
      } else {
        console.log(`[Stage 2] Sign discarded: ${result.reason} (confidence: ${(result.confidence * 100).toFixed(1)}%)`);
      }

      // Callback with result
      if (onPrediction) {
        onPrediction(result);
      }
    } catch (error) {
      console.error('[Prediction] Frame processing failed:', error);
    }

    // Schedule next frame if still enabled
    if (enabled && isModelReady) {
      animationFrameRef.current = requestAnimationFrame(processVideoFrame);
    }
  }, [videoRef, enabled, isModelReady, predictionEngine, onPrediction]);

  /**
   * Start/stop prediction loop based on model readiness and enabled state
   */
  useEffect(() => {
    if (enabled && isModelReady && !isModelLoading) {
      // Model is ready, start processing frames
      animationFrameRef.current = requestAnimationFrame(processVideoFrame);
    }

    return () => {
      // Cleanup animation frame
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [enabled, isModelReady, isModelLoading, processVideoFrame]);

  return (
    <div style={{ display: 'none' }}>
      {/* Hidden canvas for frame processing */}
      <canvas ref={canvasRef} style={{ display: 'none' }} />

      {/* Debug info */}
      {process.env.NODE_ENV === 'development' && (
        <div style={{
          position: 'fixed',
          bottom: 20,
          right: 20,
          background: 'rgba(0, 0, 0, 0.8)',
          color: '#fff',
          padding: '10px 15px',
          borderRadius: '8px',
          fontSize: '12px',
          zIndex: 9999,
          fontFamily: 'monospace',
        }}>
          <div>Model Loading: {isModelLoading ? '⏳' : '✓'}</div>
          <div>Model Ready: {isModelReady ? '✓' : '✗'}</div>
          {modelError && <div style={{ color: '#ff6b6b' }}>Error: {modelError.message}</div>}
          <div>Prediction Engine: {predictionEngine ? '✓' : '✗'}</div>
          <div>Enabled: {enabled ? 'Yes' : 'No'}</div>
        </div>
      )}
    </div>
  );
}
