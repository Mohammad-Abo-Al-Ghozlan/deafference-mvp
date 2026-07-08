export type ErrorScreenType = 'camera_denied' | 'browser_unsupported' | 'no_signs_detected';

export type CameraPermissionStatus = 'granted' | 'denied' | 'prompted';

export interface ErrorScreenConfig {
  title: string;
  description: string;
  icon: string;
  actionText: string;
}

export interface BrowserSupportChecks {
  hasWebRTC: boolean;
  hasMediaDevices: boolean;
  hasWebGL: boolean;
}

export const ERROR_SCREEN_MESSAGES: Record<ErrorScreenType, ErrorScreenConfig> = {
  camera_denied: {
    title: 'Camera Access Denied',
    description:
      'We need camera access to parse your ASL (American Sign Language) gestures. Please grant camera permission to continue.',
    icon: '🚫',
    actionText: 'Grant Camera Permission',
  },
  browser_unsupported: {
    title: 'Browser Not Supported',
    description:
      'Your browser lacks the required APIs for our sign language recognition system (WebRTC, MediaDevices, or WebGL).',
    icon: '❌',
    actionText: 'Download Compatible Browser',
  },
  no_signs_detected: {
    title: 'Still Gesturing?',
    description: "We haven't detected any sign language recently. Keep the camera pointed at your hands.",
    icon: '👋',
    actionText: 'Keep Listening',
  },
};

export const BROWSER_RECOMMENDATIONS = [
  {
    name: 'Google Chrome',
    emoji: '🌐',
    url: 'https://www.google.com/chrome/',
  },
  {
    name: 'Microsoft Edge',
    emoji: '⚡',
    url: 'https://www.microsoft.com/edge',
  },
  {
    name: 'Apple Safari',
    emoji: '🧭',
    url: 'https://www.apple.com/safari/',
  },
];

export const CAMERA_PERMISSION_INSTRUCTIONS: Record<
  string,
  { steps: string[] }
> = {
  chrome: {
    steps: [
      '1. Look for the lock icon or camera icon in the address bar',
      '2. Click on it to open site settings',
      '3. Find "Camera" in the permissions list',
      '4. Change from "Block" to "Allow"',
      '5. Reload the page',
    ],
  },
  firefox: {
    steps: [
      '1. Click the lock icon in the address bar',
      '2. Select "Permissions" or "Connection settings"',
      '3. Find "Camera" in the permissions',
      '4. Change it to "Allow"',
      '5. Reload the page',
    ],
  },
  safari: {
    steps: [
      '1. Go to Safari → Preferences',
      '2. Click the "Websites" tab',
      '3. Select "Camera" from the left sidebar',
      '4. Find this website in the list',
      '5. Change permission to "Allow"',
    ],
  },
  edge: {
    steps: [
      '1. Look for the lock or camera icon in the address bar',
      '2. Click on it to open site settings',
      '3. Find "Camera" permissions',
      '4. Change from "Block" to "Allow"',
      '5. Reload the page',
    ],
  },
};
