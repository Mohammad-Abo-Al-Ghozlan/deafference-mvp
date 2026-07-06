// types/mock-events.ts
/**
 * Event types and payloads for the mock ML inference simulator
 */

export type MockEventType = 'SIGN_RECOGNIZED' | 'SIGN_DISCARDED';

export interface SignRecognizedPayload {
  label: string;
  confidence: number;
  timestamp: number;
}

export interface SignDiscardedPayload {
  reason: 'low_confidence' | 'gesture_incomplete' | 'no_hand_detected' | 'multiple_hands';
  confidence: number;
  timestamp: number;
}

export type MockEventPayload = SignRecognizedPayload | SignDiscardedPayload;

export interface MockEvent {
  type: MockEventType;
  payload: MockEventPayload;
}

export interface MockEventCallback {
  (event: MockEvent): void;
}

export const MOCK_ASL_VOCABULARY = [
  'Hello',
  'Thank you',
  'Please',
  'Good morning',
  'Good night',
  'Help',
  'Water',
  'Food',
  'Bathroom',
  'Goodbye',
  'Yes',
  'No',
  'More',
  'Stop',
  'Sorry',
  'Welcome',
  'Friend',
  'Family',
  'Love',
  'Happy',
  'Sad',
  'Tired',
  'Hungry',
  'Beautiful',
  'Important',
] as const;

export type MockASLTerm = typeof MOCK_ASL_VOCABULARY[number];

export const DISCARD_REASONS = [
  'low_confidence',
  'gesture_incomplete',
  'no_hand_detected',
  'multiple_hands',
] as const;

export type DiscardReason = typeof DISCARD_REASONS[number];
