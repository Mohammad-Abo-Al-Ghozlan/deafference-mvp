# Camera Permission API - Implementation Details

## Architecture Overview

This is a **three-tier architecture** with clear separation of concerns:

```
Request Flow
─────────────
    ↓
┌─────────────────────────────────┐
│ Express Routes (userRoutes.ts)  │  ← Defines endpoints
└──────────────┬──────────────────┘
               ↓
┌─────────────────────────────────┐
│ Controller (CameraPermission... │  ← Validates & processes
│ Controller.ts)                  │
└──────────────┬──────────────────┘
               ↓
┌─────────────────────────────────┐
│ Service (CameraPermission...    │  ← Database operations
│ Service.ts)                     │
└──────────────┬──────────────────┘
               ↓
┌─────────────────────────────────┐
│ Prisma ORM → PostgreSQL         │  ← Data persistence
└─────────────────────────────────┘
```

---

## Type System

### 1. **Enums - PermissionStatus**
Located in [src/types/permissions.ts](src/types/permissions.ts)

```typescript
export enum PermissionStatus {
  GRANTED = "granted",
  DENIED = "denied",
  DISMISSED = "dismissed",
}
```

**Why enum?**
- Type-safe at compile time and runtime
- IDE autocomplete support
- Prevents invalid values

---

### 2. **Interfaces - Request/Response Types**

#### CameraPermissionRequest
```typescript
interface CameraPermissionRequest {
  userId: string;      // User identifier
  status: PermissionStatus;  // One of: granted, denied, dismissed
  updatedAt: Date;     // ISO timestamp
}
```

#### CameraPermissionResponse
```typescript
interface CameraPermissionResponse {
  success: boolean;
  data?: {
    id: string;
    userId: string;
    status: PermissionStatus;
    updatedAt: Date;
    createdAt: Date;
  };
  error?: {
    code: string;
    message: string;
  };
}
```

---

## Validation Layer (Zod)

Located in [src/types/validation.ts](src/types/validation.ts)

### Why Zod?
- Runtime validation (catch errors before they reach database)
- Helpful error messages
- Type inference (`z.infer<typeof Schema>`)
- Safe parsing with `.safeParse()`

### Schema Validation

```typescript
CameraPermissionRequestSchema = z.object({
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
```

**Validations:**
- ✅ `userId`: Required, non-empty, max 255 chars
- ✅ `status`: One of three enum values only
- ✅ `updatedAt`: Valid ISO date, not in future

---

## Controller Implementation

Located in [src/controllers/CameraPermissionController.ts](src/controllers/CameraPermissionController.ts)

### Method: `updateCameraPermission()`

```typescript
static async updateCameraPermission(
  req: Request,
  res: Response<CameraPermissionResponse>
): Promise<void>
```

**Flow:**
1. **Validate** request body with Zod
2. **Return 400** if validation fails
3. **Call service** to upsert to database
4. **Return 200** with created/updated data
5. **Catch errors** and return 500

**Key Points:**
- Type-safe request/response with generics
- Never trusts client data directly
- Explicit error handling
- Returns appropriate HTTP status codes

### Method: `getCameraPermission()`

```typescript
static async getCameraPermission(
  req: Request<{ userId: string }>,
  res: Response<CameraPermissionResponse>
): Promise<void>
```

**Flow:**
1. **Extract and validate** userId from path params
2. **Query database** via service
3. **Return 404** if not found
4. **Return 200** with data if found
5. **Return 500** on errors

---

## Service Layer (Business Logic)

Located in [src/services/CameraPermissionService.ts](src/services/CameraPermissionService.ts)

### Static Method Pattern

All methods are static, allowing direct usage without instantiation:

```typescript
const result = await CameraPermissionService.upsertPermission(userId, status, updatedAt);
```

### Method: `upsertPermission()`

**Purpose:** Update if exists, insert if new (atomic operation)

```typescript
static async upsertPermission(
  userId: string,
  status: PermissionStatus,
  updatedAt: Date
): Promise<CameraPermissionDB>
```

**SQL-like operation:**
```sql
INSERT INTO camera_permissions (userId, status, updatedAt)
VALUES ('user-123', 'granted', '2024-01-15...')
ON CONFLICT (userId) DO UPDATE
SET status = EXCLUDED.status, updatedAt = EXCLUDED.updatedAt;
```

**Prisma equivalent:**
```typescript
await prisma.cameraPermission.upsert({
  where: { userId },
  update: { status, updatedAt },
  create: { userId, status, updatedAt }
});
```

### Method: `getPermission()`

```typescript
static async getPermission(userId: string): Promise<CameraPermissionDB | null>
```

- Returns record if found, `null` otherwise
- Does NOT throw on missing data
- Throws on actual database errors

### Error Handling in Service

```typescript
catch (error) {
  console.error("Database error:", error);
  throw new Error(`Failed to upsert camera permission: ${...}`);
}
```

**Why throw?**
- Errors bubble to controller
- Controller returns 500 status
- Caller knows operation failed

---

## Database Schema (Prisma)

Located in [prisma/schema.prisma](prisma/schema.prisma)

```prisma
model CameraPermission {
  id        String   @id @default(cuid())        // Unique ID
  userId    String   @unique                     // Enforces one record per user
  status    String   // "granted" | "denied" | "dismissed"
  updatedAt DateTime @updatedAt                  // Auto-updated on changes
  createdAt DateTime @default(now())             // Set on creation
  
  @@index([userId])   // Optimize queries by userId
  @@index([status])   // Optimize filtering by status
  @@map("camera_permissions")  // Table name
}
```

**Key Features:**
- ✅ `@unique` on userId ensures one record per user
- ✅ `@updatedAt` automatically manages timestamp
- ✅ `@default(cuid())` generates unique IDs
- ✅ Indexes improve query performance
- ✅ Timestamp tracking for audit trail

---

## API Endpoint Details

### POST /api/users/camera-permission

**Responsibility:** Create or update permission

**Request:**
```json
{
  "userId": "user-12345",
  "status": "granted",
  "updatedAt": "2024-01-15T10:30:00Z"
}
```

**Response Scenarios:**

1. **Success (200):**
   ```json
   {
     "success": true,
     "data": { ... }
   }
   ```

2. **Validation Error (400):**
   ```json
   {
     "success": false,
     "error": {
       "code": "VALIDATION_ERROR",
       "message": "Request validation failed"
     }
   }
   ```

3. **Server Error (500):**
   ```json
   {
     "success": false,
     "error": {
       "code": "INTERNAL_SERVER_ERROR",
       "message": "Failed to upsert camera permission: ..."
     }
   }
   ```

---

### GET /api/users/:userId/camera-permission

**Responsibility:** Retrieve user's permission

**Response Scenarios:**

1. **Found (200):**
   ```json
   {
     "success": true,
     "data": { ... }
   }
   ```

2. **Not Found (404):**
   ```json
   {
     "success": false,
     "error": {
       "code": "NOT_FOUND",
       "message": "Camera permission record not found"
     }
   }
   ```

3. **Invalid User ID (400):**
   ```json
   {
     "success": false,
     "error": {
       "code": "VALIDATION_ERROR",
       "message": "User ID is required"
     }
   }
   ```

---

## Error Handling Strategy

### 1. **Validation Errors (400)**
- Invalid request format
- Missing required fields
- Invalid enum values
- Handled in controller

### 2. **Not Found Errors (404)**
- Resource doesn't exist
- Handled in controller
- Return specific error message

### 3. **Server Errors (500)**
- Database connection issues
- Unexpected runtime errors
- Caught in try-catch blocks
- Generic message in production mode

### 4. **Global Error Handler**
Middleware in [src/index.ts](src/index.ts):
```typescript
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  // Catches unhandled errors
  // Returns 500 status
  // Hides details in production
});
```

---

## Type Safety Throughout

### Example: Request Type

```typescript
app.post('/api/users/camera-permission', 
  (req: Request, res: Response<CameraPermissionResponse>) => {
    // ✅ TypeScript knows response type
    // ✅ IDE provides autocomplete
    // ✅ Compile-time safety
  }
);
```

### Example: Service Call

```typescript
const permission = await CameraPermissionService.upsertPermission(
  userId,    // ← Must be string
  status,    // ← Must be PermissionStatus enum
  updatedAt  // ← Must be Date
);
// permission ← Always CameraPermissionDB | never null
```

---

## Database Indexes

Indexes improve performance:

```prisma
@@index([userId])   // Fast: SELECT WHERE userId = ?
@@index([status])   // Fast: SELECT WHERE status = ?
```

**Example Query Performance:**
- Without index: O(n) - scans all rows
- With index: O(log n) - tree-based lookup

---

## Security Considerations

### ✅ Implemented
1. **Input Validation** - Zod validates all inputs
2. **Type Safety** - TypeScript prevents type errors
3. **Parameterized Queries** - Prisma uses safe queries (no SQL injection)
4. **Error Masking** - Production doesn't expose internals

### 🔒 TODO (Production)
1. **Authentication** - Verify user identity (JWT, OAuth, etc.)
2. **Authorization** - Check user can modify their own record only
3. **Rate Limiting** - Prevent abuse (express-rate-limit)
4. **CORS** - Restrict cross-origin requests
5. **Logging** - Track all API calls for audit trail

---

## Performance Optimizations

1. **Database Indexes** - Speeds up queries
2. **Unique Constraint** - Prevents duplicate data
3. **Compiled TypeScript** - Type checks at build time
4. **Express Middleware** - Efficient request handling

---

## Testing Strategy

### Unit Tests (TODO)
- Controller methods with mocked service
- Service methods with mocked database
- Validation schemas with various inputs

### Integration Tests (TODO)
- Full request → response flow
- Database operations
- Error scenarios

### cURL Tests (Provided)
- See [test-api.sh](test-api.sh)
- Test all endpoints
- Test error cases

---

## Deployment Checklist

- [ ] Install Node.js on server
- [ ] Set up PostgreSQL database
- [ ] Configure `.env` with production values
- [ ] Run `npm install --production`
- [ ] Run `npm run db:push` (migrations)
- [ ] Run `npm run build`
- [ ] Start with `npm start`
- [ ] Set up monitoring and logging
- [ ] Configure CI/CD pipeline
- [ ] Add authentication/authorization
- [ ] Set up HTTPS/SSL
- [ ] Configure rate limiting
- [ ] Add comprehensive error logging

---

## References

- [Express.js Documentation](https://expressjs.com/)
- [Prisma Documentation](https://www.prisma.io/docs/)
- [TypeScript Documentation](https://www.typescriptlang.org/docs/)
- [Zod Documentation](https://zod.dev/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

