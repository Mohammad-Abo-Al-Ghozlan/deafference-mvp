/**
 * Camera Permission Types and Enums
 * Defines strict types for camera permission state tracking
 */

/**
 * Enum for camera permission states
 */
export enum PermissionStatus {
  GRANTED = "granted",
  DENIED = "denied",
  DISMISSED = "dismissed",
}

/**
 * Type guard to validate if a string is a valid PermissionStatus
 */
export const isValidPermissionStatus = (value: unknown): value is PermissionStatus => {
  return Object.values(PermissionStatus).includes(value as PermissionStatus);
};

/**
 * Request body interface for camera permission update
 */
export interface CameraPermissionRequest {
  userId: string;
  status: PermissionStatus;
  updatedAt: Date;
}

/**
 * Response interface for API responses
 */
export interface CameraPermissionResponse {
  success: boolean;
  data?: {
    id: string;
    userId: string;
    status: PermissionStatus;
    updatedAt: Date;
    createdAt: Date;
  };
  error?: {
    code: string;
    message: string;
  };
}

/**
 * Database model type (from Prisma)
 */
export interface CameraPermissionDB {
  id: string;
  userId: string;
  status: PermissionStatus;
  updatedAt: Date;
  createdAt: Date;
}
