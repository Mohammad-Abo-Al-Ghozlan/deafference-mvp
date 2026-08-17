// controllers/cameraPermissionController.ts
import { Response } from 'express';
import { Prisma } from '@prisma/client';
import { prisma } from '../lib/prisma';
import { ValidatedRequest } from '../middleware/validators';
import { CameraPermissionResponse, ApiResponse } from '../types/camera-permission';

export const updateCameraPermission = async (
  req: ValidatedRequest,
  res: Response<ApiResponse<CameraPermissionResponse>>
): Promise<void> => {
  try {
    if (!req.validatedBody) {
      res.status(400).json({
        success: false,
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Request validation failed',
        },
      });
      return;
    }

    const { userId, status } = req.validatedBody;

    // Upsert the camera permission record
    const cameraPermission = await prisma.cameraPermission.upsert({
      where: { userId },
      update: { status },
      create: {
        userId,
        status,
      },
    });

    // Format the response
    const response: CameraPermissionResponse = {
      id: cameraPermission.id,
      userId: cameraPermission.userId,
      status: cameraPermission.status as 'granted' | 'denied' | 'prompted',
      createdAt: cameraPermission.createdAt.toISOString(),
      updatedAt: cameraPermission.updatedAt.toISOString(),
    };

    res.status(200).json({
      success: true,
      data: response,
    });
  } catch (error) {
    console.error('Camera permission update error:', error);

    if (error instanceof Prisma.PrismaClientKnownRequestError) {
      // Foreign-key failure (P2003): the userId doesn't reference an existing
      // user. Previously this fell through to a 500 on perfectly normal input
      // (a client with a stale userId). Return a clean 404 instead.
      if (error.code === 'P2003') {
        res.status(404).json({
          success: false,
          error: {
            code: 'USER_NOT_FOUND',
            message: 'No user exists for the provided userId',
          },
        });
        return;
      }
      // Unique-constraint conflict (P2002) — matched by code, not message text.
      if (error.code === 'P2002') {
        res.status(409).json({
          success: false,
          error: {
            code: 'CONFLICT',
            message: 'Camera permission record already exists for this user',
          },
        });
        return;
      }
    }

    // Generic database error
    res.status(500).json({
      success: false,
      error: {
        code: 'DATABASE_ERROR',
        message: 'Failed to update camera permission. Please try again later.',
      },
    });
  }
};

export const getCameraPermission = async (
  req: ValidatedRequest,
  res: Response<ApiResponse<CameraPermissionResponse>>
): Promise<void> => {
  try {
    // Require the WHOLE param to be digits — parseInt("5abc") would silently
    // return 5 and query the wrong user.
    const rawParam = Array.isArray(req.params.userId)
      ? req.params.userId[0]
      : req.params.userId;
    const userId = /^\d+$/.test(rawParam ?? "") ? Number(rawParam) : NaN;

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

    const cameraPermission = await prisma.cameraPermission.findUnique({
      where: { userId },
    });

    if (!cameraPermission) {
      res.status(404).json({
        success: false,
        error: {
          code: 'NOT_FOUND',
          message: 'Camera permission record not found',
        },
      });
      return;
    }

    const response: CameraPermissionResponse = {
      id: cameraPermission.id,
      userId: cameraPermission.userId,
      status: cameraPermission.status as 'granted' | 'denied' | 'prompted',
      createdAt: cameraPermission.createdAt.toISOString(),
      updatedAt: cameraPermission.updatedAt.toISOString(),
    };

    res.status(200).json({
      success: true,
      data: response,
    });
  } catch (error) {
    console.error('Camera permission fetch error:', error);

    res.status(500).json({
      success: false,
      error: {
        code: 'DATABASE_ERROR',
        message: 'Failed to fetch camera permission. Please try again later.',
      },
    });
  }
};
