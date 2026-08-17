// controllers/userController.ts
import { Response } from 'express';
import { Prisma } from '@prisma/client';
import { prisma } from '../lib/prisma';
import { ValidatedUserRequest } from '../middleware/validators';
import { UserResponse } from '../types/user';
import { ApiResponse } from '../types/camera-permission';

export const createUser = async (
  req: ValidatedUserRequest,
  res: Response<ApiResponse<UserResponse>>
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

    const { email, name } = req.validatedBody;

    // Create the user record
    const user = await prisma.user.create({
      data: {
        email,
        ...(name !== undefined ? { name } : {}),
      },
    });

    // Format the response
    const response: UserResponse = {
      id: user.id,
      email: user.email,
      name: user.name,
      createdAt: user.createdAt.toISOString(),
      updatedAt: user.updatedAt.toISOString(),
    };

    res.status(201).json({
      success: true,
      data: response,
    });
  } catch (error) {
    console.error('User creation error:', error);

    // Detect duplicate-email by Prisma error CODE (P2002), not message text —
    // message wording is version/locale-dependent and would silently 500.
    if (
      error instanceof Prisma.PrismaClientKnownRequestError &&
      error.code === 'P2002'
    ) {
      res.status(409).json({
        success: false,
        error: {
          code: 'CONFLICT',
          message: 'A user with this email already exists',
        },
      });
      return;
    }

    // Generic database error
    res.status(500).json({
      success: false,
      error: {
        code: 'DATABASE_ERROR',
        message: 'Failed to create user. Please try again later.',
      },
    });
  }
};
