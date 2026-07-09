/**
 * Camera Permission Routes
 * Defines API endpoints for camera permission tracking
 */

import { Router } from "express";
import CameraPermissionController from "../controllers/CameraPermissionController";

const router = Router();

/**
 * POST /api/users/camera-permission
 * Update or create camera permission record
 */
router.post(
  "/camera-permission",
  CameraPermissionController.updateCameraPermission
);

/**
 * GET /api/users/:userId/camera-permission
 * Retrieve camera permission for a user
 */
router.get(
  "/:userId/camera-permission",
  CameraPermissionController.getCameraPermission
);

export default router;
