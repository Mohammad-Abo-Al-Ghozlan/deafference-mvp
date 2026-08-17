// routes/cameraPermissionRoutes.ts
import { Router } from 'express';
import { validateCameraPermissionPayload } from '../middleware/validators';
import { requireAuth } from '../middleware/auth';
import {
  updateCameraPermission,
  getCameraPermission,
} from '../controllers/cameraPermissionController';

const router = Router();

/**
 * POST /api/users/camera-permission
 * Update or create a camera permission record for a user
 * @param {number} userId - The user ID
 * @param {string} status - The permission status (granted, denied, prompted)
 */
router.post(
  '/camera-permission',
  requireAuth,
  validateCameraPermissionPayload,
  updateCameraPermission
);

/**
 * GET /api/users/camera-permission/:userId
 * Retrieve camera permission status for a specific user
 * @param {number} userId - The user ID
 */
router.get('/camera-permission/:userId', requireAuth, getCameraPermission);

export default router;
