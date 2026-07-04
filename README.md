# Camera Permission API - Setup & Testing Guide

## Project Overview

This is a production-grade backend API built with **TypeScript**, **Node.js/Express**, **Prisma**, and **PostgreSQL** for tracking camera permission states.

### Features
- ✅ Strongly-typed TypeScript implementation
- ✅ Express.js REST API endpoints
- ✅ Prisma ORM with PostgreSQL
- ✅ Request validation with Zod
- ✅ Upsert database operations
- ✅ Comprehensive error handling
- ✅ Health check endpoint

---

## Prerequisites

- **Node.js** >= 16.x
- **npm** or **yarn**
- **PostgreSQL** >= 12.x (local or remote)
- **Prisma CLI** (installed via npm)

---

## Installation & Setup

### 1. Install Dependencies

```bash
npm install
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env` and update the database URL:

```bash
cp .env.example .env
```

Edit `.env`:

```env
DATABASE_URL="postgresql://user:password@localhost:5432/camera_permissions_db"
PORT=3000
NODE_ENV=development
```

**PostgreSQL Connection String Format:**
```
postgresql://[user]:[password]@[host]:[port]/[database]
```

### 3. Set Up Database

#### Create PostgreSQL Database

```bash
# Using psql (if PostgreSQL is installed locally)
createdb camera_permissions_db

# Or via PostgreSQL client:
CREATE DATABASE camera_permissions_db;
```

#### Initialize Prisma Schema

```bash
# Generate Prisma Client
npm run db:generate

# Push schema to database
npm run db:push
```

This will create the `camera_permissions` table automatically.

---

## Running the Server

### Development Mode (with auto-reload)

```bash
npm run dev
```

Server will start on `http://localhost:3000`

### Production Mode

```bash
npm run build
npm start
```

---

## API Endpoints

### 1. Health Check
```bash
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "environment": "development"
}
```

---

### 2. Update/Create Camera Permission (Upsert)
```bash
POST /api/users/camera-permission
```

**Request Body:**
```json
{
  "userId": "user-12345",
  "status": "granted",
  "updatedAt": "2024-01-15T10:30:00.000Z"
}
```

**Valid Status Values:**
- `"granted"` - User granted camera permission
- `"denied"` - User denied camera permission
- `"dismissed"` - User dismissed the permission prompt

**Success Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "clq1a2b3c4d5e6f7g8h9i0j1",
    "userId": "user-12345",
    "status": "granted",
    "updatedAt": "2024-01-15T10:30:00.000Z",
    "createdAt": "2024-01-15T10:30:00.000Z"
  }
}
```

**Validation Error Response (400 Bad Request):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed"
  }
}
```

**Server Error Response (500 Internal Server Error):**
```json
{
  "success": false,
  "error": {
    "code": "INTERNAL_SERVER_ERROR",
    "message": "Failed to upsert camera permission: <error details>"
  }
}
```

---

### 3. Get Camera Permission
```bash
GET /api/users/:userId/camera-permission
```

**Example:**
```bash
GET /api/users/user-12345/camera-permission
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "id": "clq1a2b3c4d5e6f7g8h9i0j1",
    "userId": "user-12345",
    "status": "granted",
    "updatedAt": "2024-01-15T10:30:00.000Z",
    "createdAt": "2024-01-15T10:30:00.000Z"
  }
}
```

**Not Found Response (404):**
```json
{
  "success": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "Camera permission record not found"
  }
}
```

---

## Testing with cURL

### Test 1: Health Check
```bash
curl -X GET http://localhost:3000/health
```

### Test 2: Create New Permission
```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-12345",
    "status": "granted",
    "updatedAt": "2024-01-15T10:30:00Z"
  }'
```

### Test 3: Update Existing Permission
```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-12345",
    "status": "denied",
    "updatedAt": "2024-01-15T11:00:00Z"
  }'
```

### Test 4: Retrieve Permission
```bash
curl -X GET http://localhost:3000/api/users/user-12345/camera-permission
```

### Test 5: Invalid Status (Should Fail - 400)
```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-12345",
    "status": "invalid_status",
    "updatedAt": "2024-01-15T10:30:00Z"
  }'
```

### Test 6: Missing Required Field (Should Fail - 400)
```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "status": "granted",
    "updatedAt": "2024-01-15T10:30:00Z"
  }'
```

---

## Testing with Postman

1. **Create New Request** → POST
2. **URL:** `http://localhost:3000/api/users/camera-permission`
3. **Headers:** `Content-Type: application/json`
4. **Body** (raw JSON):
   ```json
   {
     "userId": "user-12345",
     "status": "granted",
     "updatedAt": "2024-01-15T10:30:00Z"
   }
   ```
5. **Send** → View response

---

## Project Structure

```
deafference-sign-ai-mvp-1/
├── src/
│   ├── index.ts                          # Express app entry point
│   ├── types/
│   │   ├── permissions.ts                # Type definitions & enums
│   │   └── validation.ts                 # Zod validation schemas
│   ├── controllers/
│   │   └── CameraPermissionController.ts # Request handlers
│   ├── services/
│   │   └── CameraPermissionService.ts    # Database logic
│   └── routes/
│       └── userRoutes.ts                 # API endpoints
├── prisma/
│   └── schema.prisma                     # Database schema
├── dist/                                 # Compiled JavaScript (after build)
├── package.json                          # Project dependencies
├── tsconfig.json                         # TypeScript config
├── .env                                  # Environment variables
└── README.md                             # This file
```

---

## Type Safety & Validation

### Type Definitions

The project uses strict TypeScript typing:

```typescript
// Permission Status Enum
export enum PermissionStatus {
  GRANTED = "granted",
  DENIED = "denied",
  DISMISSED = "dismissed",
}

// Request Interface
export interface CameraPermissionRequest {
  userId: string;
  status: PermissionStatus;
  updatedAt: Date;
}
```

### Runtime Validation

Requests are validated using **Zod** schema:
- ✅ `userId`: non-empty string, max 255 chars
- ✅ `status`: must be one of enum values
- ✅ `updatedAt`: must be valid ISO date, not in future

---

## Database Operations

### Upsert Logic

The `CameraPermissionService.upsertPermission()` method:
- **If user exists:** Updates the `status` and `updatedAt` fields
- **If user doesn't exist:** Creates new record with all fields

```typescript
const result = await prisma.cameraPermission.upsert({
  where: { userId },
  update: { status, updatedAt },
  create: { userId, status, updatedAt }
});
```

---

## Error Handling

All errors are caught and returned with appropriate HTTP status codes:

| Status | Code | Meaning |
|--------|------|---------|
| 400 | VALIDATION_ERROR | Invalid request body |
| 404 | NOT_FOUND | Resource not found |
| 500 | INTERNAL_SERVER_ERROR | Server error |

---

## Building for Production

```bash
# Compile TypeScript to JavaScript
npm run build

# Output is in ./dist directory
ls -la dist/
```

---

## Troubleshooting

### Issue: Database Connection Error
- **Check:** `DATABASE_URL` in `.env`
- **Verify:** PostgreSQL server is running
- **Test:** `psql -U user -d camera_permissions_db`

### Issue: Prisma Client Not Generated
```bash
npm run db:generate
```

### Issue: Table Not Found
```bash
npm run db:push
```

### Issue: Port Already in Use
```bash
# Change PORT in .env or specify when running
PORT=3001 npm run dev
```

---

## Security Considerations

- ✅ Validates all input using Zod
- ✅ Type-safe database operations with Prisma
- ✅ No SQL injection (parameterized queries)
- ✅ Error messages don't expose sensitive info in production
- 🔒 **TODO:** Add authentication middleware
- 🔒 **TODO:** Add rate limiting
- 🔒 **TODO:** Add CORS configuration

---

## Dependencies

- **express** - Web framework
- **@prisma/client** - ORM for database
- **zod** - Schema validation
- **dotenv** - Environment variables
- **typescript** - Type safety
- **ts-node** - Run TypeScript directly

---

## Next Steps

1. Set up database
2. Install dependencies: `npm install`
3. Configure `.env`
4. Run migrations: `npm run db:push`
5. Start server: `npm run dev`
6. Test endpoints with cURL or Postman

---

## License

ISC
