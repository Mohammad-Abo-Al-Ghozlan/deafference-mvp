// middleware/validators.ts
import { Request, Response, NextFunction } from 'express';
import { CameraPermissionRequest, CameraPermissionStatus } from '../types/camera-permission';

export interface ValidatedRequest extends Request {
  validatedBody?: CameraPermissionRequest;
}

const VALID_STATUSES: CameraPermissionStatus[] = ['granted', 'denied', 'prompted'];

export const validateCameraPermissionPayload = (
  req: ValidatedRequest,
  res: Response,
  next: NextFunction
): void => {
  try {
    const { userId, status } = req.body;

    // Validate userId
    if (userId === undefined || userId === null) {
      res.status(400).json({
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: 'userId is required',
        },
      });
      return;
    }

    if (!Number.isInteger(userId) || userId <= 0) {
      res.status(400).json({
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: 'userId must be a positive integer',
        },
      });
      return;
    }

    // Validate status
    if (!status) {
      res.status(400).json({
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: 'status is required',
        },
      });
      return;
    }

    if (!VALID_STATUSES.includes(status as CameraPermissionStatus)) {
      res.status(400).json({
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: `status must be one of: ${VALID_STATUSES.join(', ')}`,
        },
      });
      return;
    }

    // Attach validated data to request
    req.validatedBody = {
      userId,
      status: status as CameraPermissionStatus,
    };

    next();
  } catch (error) {
    res.status(400).json({
      success: false,
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Invalid request payload',
      },
    });
  }
};
