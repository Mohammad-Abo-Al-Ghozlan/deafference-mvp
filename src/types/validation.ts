/**
 * Request validation schemas using Zod
 */

import { z } from "zod";
import { PermissionStatus } from "./permissions";

/**
 * Validation schema for camera permission requests
 */
export const CameraPermissionRequestSchema = z.object({
  userId: z
    .string()
    .min(1, "User ID is required")
    .max(255, "User ID must not exceed 255 characters"),
  status: z
    .enum([PermissionStatus.GRANTED, PermissionStatus.DENIED, PermissionStatus.DISMISSED])
    .refine(
      (value) => Object.values(PermissionStatus).includes(value),
      "Status must be one of: granted, denied, dismissed"
    ),
  updatedAt: z
    .date()
    .or(z.string().datetime())
    .transform((val) => (typeof val === "string" ? new Date(val) : val))
    .refine((date) => date <= new Date(), "updatedAt cannot be in the future"),
});

export type CameraPermissionRequestInput = z.infer<typeof CameraPermissionRequestSchema>;
