// server/lib/prisma.ts
// A single shared PrismaClient. Instantiating one client per controller (the
// previous approach) opened a fresh connection pool on every `tsx watch` reload,
// which exhausts Postgres connections in dev and doubles pools in prod.
import { PrismaClient } from '@prisma/client';

const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

export const prisma = globalForPrisma.prisma ?? new PrismaClient();

if (process.env.NODE_ENV !== 'production') {
  globalForPrisma.prisma = prisma;
}
