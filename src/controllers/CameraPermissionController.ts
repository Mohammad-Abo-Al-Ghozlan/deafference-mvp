/**
 * Camera Permission Controller
 * Handles HTTP request logic for camera permission endpoints
 */

import { Request, Response } from "express";
import { CameraPermissionRequestSchema } from "../types/validation";
import CameraPermissionService from "../services/CameraPermissionService";
import { CameraPermissionResponse } from "../types/permissions";

export class CameraPermissionController {
  /**
   * Update camera permission status
   * POST /api/users/camera-permission
   * @param req - Express request with body containing userId, status, updatedAt
   * @param res - Express response
   */
  static async updateCameraPermission(
    req: Request,
    res: Response<CameraPermissionResponse>
  ): Promise<void> {
    try {
      // Validate request body
      const validationResult = CameraPermissionRequestSchema.safeParse(req.body);

      if (!validationResult.success) {
        res.status(400).json({
          success: false,
          error: {
            code: "VALIDATION_ERROR",
            message: "Request validation failed",
          },
        });
        return;
      }

      const { userId, status, updatedAt } = validationResult.data;

      // Call service to upsert permission
      const permission = await CameraPermissionService.upsertPermission(
        userId,
        status,
        updatedAt
      );

      res.status(200).json({
        success: true,
        data: permission,
      });
    } catch (error) {
      console.error("Error in updateCameraPermission:", error);

      res.status(500).json({
        success: false,
        error: {
          code: "INTERNAL_SERVER_ERROR",
          message: error instanceof Error ? error.message : "An unexpected error occurred",
        },
      });
    }
  }

  /**
   * Get camera permission for a user
   * GET /api/users/:userId/camera-permission
   * @param req - Express request with userId in params
   * @param res - Express response
   */
  static async getCameraPermission(
    req: Request<{ userId: string }>,
    res: Response<CameraPermissionResponse>
  ): Promise<void> {
    try {
      const { userId } = req.params;

      // Basic validation
      if (!userId || userId.trim() === "") {
        res.status(400).json({
          success: false,
          error: {
            code: "VALIDATION_ERROR",
            message: "User ID is required",
          },
        });
        return;
      }

      const permission = await CameraPermissionService.getPermission(userId);

      if (!permission) {
        res.status(404).json({
          success: false,
          error: {
            code: "NOT_FOUND",
            message: "Camera permission record not found",
          },
        });
        return;
      }

      res.status(200).json({
        success: true,
        data: permission,
      });
    } catch (error) {
      console.error("Error in getCameraPermission:", error);

      res.status(500).json({
        success: false,
        error: {
          code: "INTERNAL_SERVER_ERROR",
          message: error instanceof Error ? error.message : "An unexpected error occurred",
        },
      });
    }
  }
}

export default CameraPermissionController;
