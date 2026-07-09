/**
 * Types and interfaces for TensorFlow.js model layer
 * Defines the contract for prediction engine and model lifecycle
 */

/**
 * Prediction result from the model inference engine
 * Represents either a recognized sign or a discarded gesture
 */
export type PredictionResult =
  | {
      type: 'recognized';
      label: string;
      confidence: number;
      timestamp: number;
    }
  | {
      type: 'discarded';
      reason: 'low_confidence' | 'gesture_incomplete' | 'no_hand_detected' | 'multiple_hands';
      confidence: number;
      timestamp: number;
    };

/**
 * Video frame data input for model prediction
 * Can be a canvas, ImageData, or tensor representation
 */
export type VideoFrame = {
  data: ArrayLike | undefined;
  width: number;
  height: number;
};

/**
 * Prediction engine interface
 * Implements the model inference contract with async prediction capability
 */
export interface PredictionEngine {
  /**
   * Execute prediction on a video frame
   * @param frame - Video frame data to predict on
   * @returns Promise resolving to prediction result
   */
  predict(frame: VideoFrame): Promise<PredictionResult>;

  /**
   * Cleanup resources held by the prediction engine
   */
  dispose(): void;
}

/**
 * Model initialization state
 */
export interface ModelState {
  isModelLoading: boolean;
  isModelReady: boolean;
  modelError: Error | null;
}

/**
 * Return type for the useTensorFlowModel hook
 */
export interface UseTensorFlowModelReturn extends ModelState {
  predictionEngine: PredictionEngine | null;
}
