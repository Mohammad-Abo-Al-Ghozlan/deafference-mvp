/**
 * Database Service for Camera Permissions
 * Handles all database operations with Prisma
 */

import { PrismaClient } from "@prisma/client";
import { PermissionStatus, CameraPermissionDB } from "../types/permissions";

const prisma = new PrismaClient();

export class CameraPermissionService {
  /**
   * Upsert camera permission: updates if exists, inserts if new
   * @param userId - The user ID
   * @param status - The permission status
   * @param updatedAt - The update timestamp
   * @returns The created or updated record
   */
  static async upsertPermission(
    userId: string,
    status: PermissionStatus,
    updatedAt: Date
  ): Promise<CameraPermissionDB> {
    try {
      const result = await prisma.cameraPermission.upsert({
        where: { userId },
        update: {
          status,
          updatedAt,
        },
        create: {
          userId,
          status,
          updatedAt,
        },
      });

      return {
        id: result.id,
        userId: result.userId,
        status: result.status as PermissionStatus,
        updatedAt: result.updatedAt,
        createdAt: result.createdAt,
      };
    } catch (error) {
      console.error("Database error in upsertPermission:", error);
      throw new Error(`Failed to upsert camera permission: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  }

  /**
   * Get camera permission for a user
   * @param userId - The user ID
   * @returns The permission record or null
   */
  static async getPermission(userId: string): Promise<CameraPermissionDB | null> {
    try {
      const result = await prisma.cameraPermission.findUnique({
        where: { userId },
      });

      if (!result) return null;

      return {
        id: result.id,
        userId: result.userId,
        status: result.status as PermissionStatus,
        updatedAt: result.updatedAt,
        createdAt: result.createdAt,
      };
    } catch (error) {
      console.error("Database error in getPermission:", error);
      throw new Error(`Failed to retrieve camera permission: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  }

  /**
   * Delete camera permission for a user
   * @param userId - The user ID
   */
  static async deletePermission(userId: string): Promise<void> {
    try {
      await prisma.cameraPermission.delete({
        where: { userId },
      });
    } catch (error) {
      console.error("Database error in deletePermission:", error);
      throw new Error(`Failed to delete camera permission: ${error instanceof Error ? error.message : "Unknown error"}`);
    }
  }

  /**
   * Disconnect Prisma client
   */
  static async disconnect(): Promise<void> {
    await prisma.$disconnect();
  }
}

export default CameraPermissionService;

export default CameraPermissionService;
