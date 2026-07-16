// routes/userRoutes.ts
import { Router } from 'express';
import { validateCreateUserPayload } from '../middleware/validators';
import { createUser } from '../controllers/userController';

const router = Router();

/**
 * POST /api/users
 * Create a new user
 * @param {string} email - The user's email address (unique, required)
 * @param {string} [name] - The user's display name (optional)
 */
router.post('/', validateCreateUserPayload, createUser);

export default router;
