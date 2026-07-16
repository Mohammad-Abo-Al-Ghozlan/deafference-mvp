// middleware/validators.ts
import { Request, Response, NextFunction } from 'express';
import { CameraPermissionRequest, CameraPermissionStatus } from '../types/camera-permission';
import { CreateUserRequest } from '../types/user';

export interface ValidatedRequest extends Request {
  validatedBody?: CameraPermissionRequest;
}

export interface ValidatedUserRequest extends Request {
  validatedBody?: CreateUserRequest;
}

const VALID_STATUSES: CameraPermissionStatus[] = ['granted', 'denied', 'prompted'];

// Basic RFC-5322-ish email shape check (kept intentionally simple, mirroring
// the lightweight validation style used elsewhere in this file).
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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

export const validateCreateUserPayload = (
  req: ValidatedUserRequest,
  res: Response,
  next: NextFunction
): void => {
  try {
    const { email, name } = req.body;

    // Validate email
    if (email === undefined || email === null || email === '') {
      res.status(400).json({
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: 'email is required',
        },
      });
      return;
    }

    if (typeof email !== 'string' || !EMAIL_REGEX.test(email)) {
      res.status(400).json({
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: 'email must be a valid email address',
        },
      });
      return;
    }

    // Validate name (optional)
    if (name !== undefined && name !== null && typeof name !== 'string') {
      res.status(400).json({
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: 'name must be a string',
        },
      });
      return;
    }

    // Attach validated data to request
    const validated: CreateUserRequest = { email };
    if (typeof name === 'string') {
      validated.name = name;
    }
    req.validatedBody = validated;

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
