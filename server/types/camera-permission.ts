// types/camera-permission.ts
export type CameraPermissionStatus = 'granted' | 'denied' | 'prompted';

export interface CameraPermissionRequest {
  userId: number;
  status: CameraPermissionStatus;
}

export interface CameraPermissionResponse {
  id: number;
  userId: number;
  status: CameraPermissionStatus;
  createdAt: string;
  updatedAt: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
  };
}
