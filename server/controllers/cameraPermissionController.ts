// controllers/cameraPermissionController.ts
import { Response } from 'express';
import { PrismaClient } from '@prisma/client';
import { ValidatedRequest } from '../middleware/validators';
import { CameraPermissionResponse, ApiResponse } from '../types/camera-permission';

const prisma = new PrismaClient();

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

    // Handle Prisma validation errors
    if (error instanceof Error) {
      if (error.message.includes('Unique constraint')) {
        res.status(409).json({
          success: false,
          error: {
            code: 'CONFLICT',
            message: 'Camera permission record already exists for this user',
          },
        });
        return;
      }

      // NOTE (BE-5): This endpoint intentionally uses prisma.upsert()
      // (create-or-update), as documented on the route ("Update or create a
      // camera permission record") and reflected by its 200 (not 201)
      // response. Because upsert creates the row when it is absent, Prisma
      // never throws "Record to update not found" here, so the former 404
      // branch was unreachable dead code and has been removed.
      // A strict update-only variant would instead use prisma.update() and
      // keep the 404; we deliberately keep upsert so a permission can be set
      // before one exists (e.g. immediately after a user is created).
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
    const userIdParam = Array.isArray(req.params.userId) ? req.params.userId[0] : req.params.userId;
    const userId = parseInt(userIdParam, 10);

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
