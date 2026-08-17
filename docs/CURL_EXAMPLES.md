# Deafference API - cURL Testing Examples

## Prerequisites

- A migrated database (see the README "Backend API" section: `npx prisma migrate dev`)
- API server running on `http://localhost:4000` (`npm run server:dev`)
- `curl` command available in terminal
- `jq` (optional, for pretty-printing JSON)

> **Data model note:** `userId` is an **integer** foreign key to a `User` row.
> You must create a user first (`POST /api/users`) and use the returned integer
> `id` as the `userId` for camera-permission calls. See the full flow at the
> bottom of this file.

---

## 🔍 Quick Test Commands

### 1. Health Check

```bash
curl -X GET http://localhost:4000/health
```

**Expected Response (200):**
```json
{
  "status": "ok",
  "timestamp": "2026-07-16T10:30:00.000Z"
}
```

---

### 2. Create User

```bash
curl -X POST http://localhost:4000/api/users \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@example.com",
    "name": "Alice"
  }'
```

**Expected Response (201):**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "email": "alice@example.com",
    "name": "Alice",
    "createdAt": "2026-07-16T10:30:00.123Z",
    "updatedAt": "2026-07-16T10:30:00.123Z"
  }
}
```

> `name` is optional. The integer `id` returned here is the `userId` used below.

---

### 3. Create Camera Permission (Upsert)

`POST /api/users/camera-permission` uses **create-or-update** semantics: it
creates the record if none exists for the user, otherwise updates it. Either
way it returns **200**.

```bash
curl -X POST http://localhost:4000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": 1,
    "status": "granted"
  }'
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "userId": 1,
    "status": "granted",
    "createdAt": "2026-07-16T10:30:05.000Z",
    "updatedAt": "2026-07-16T10:30:05.000Z"
  }
}
```

---

### 4. Update Permission (Same Endpoint, Status Changed)

```bash
curl -X POST http://localhost:4000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": 1,
    "status": "denied"
  }'
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "userId": 1,
    "status": "denied",
    "createdAt": "2026-07-16T10:30:05.000Z",
    "updatedAt": "2026-07-16T10:31:00.000Z"
  }
}
```

**Note:** `createdAt` stays the same; `updatedAt` advances (managed by Prisma).

---

### 5. Get User's Permission

```bash
curl -X GET http://localhost:4000/api/users/camera-permission/1
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "userId": 1,
    "status": "denied",
    "createdAt": "2026-07-16T10:30:05.000Z",
    "updatedAt": "2026-07-16T10:31:00.000Z"
  }
}
```

---

## ❌ Error Test Cases

Every case below is reachable against the real API.

### Test 1: Create User — Missing email (400)

```bash
curl -X POST http://localhost:4000/api/users \
  -H "Content-Type: application/json" \
  -d '{ "name": "No Email" }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "email is required"
  }
}
```

---

### Test 2: Create User — Invalid email format (400)

```bash
curl -X POST http://localhost:4000/api/users \
  -H "Content-Type: application/json" \
  -d '{ "email": "not-an-email" }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "email must be a valid email address"
  }
}
```

---

### Test 3: Create User — Duplicate email (409)

Send the same email twice; the second request conflicts on the unique constraint.

```bash
curl -X POST http://localhost:4000/api/users \
  -H "Content-Type: application/json" \
  -d '{ "email": "alice@example.com" }'
```

**Expected Response (409):**
```json
{
  "success": false,
  "error": {
    "code": "CONFLICT",
    "message": "A user with this email already exists"
  }
}
```

---

### Test 4: Camera Permission — Invalid status (400)

```bash
curl -X POST http://localhost:4000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{ "userId": 1, "status": "invalid_value" }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "status must be one of: granted, denied, prompted"
  }
}
```

---

### Test 5: Camera Permission — Missing userId (400)

```bash
curl -X POST http://localhost:4000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{ "status": "granted" }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "userId is required"
  }
}
```

---

### Test 6: Camera Permission — Missing status (400)

```bash
curl -X POST http://localhost:4000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{ "userId": 1 }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "status is required"
  }
}
```

---

### Test 7: Camera Permission — Non-integer userId (400)

```bash
curl -X POST http://localhost:4000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{ "userId": "abc", "status": "granted" }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "userId must be a positive integer"
  }
}
```

---

### Test 8: Get Permission — Non-integer userId (400)

```bash
curl -X GET http://localhost:4000/api/users/camera-permission/not-a-number
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "userId must be a positive integer"
  }
}
```

---

### Test 9: Get Permission — Not found (404)

Use a valid integer with no permission record.

```bash
curl -X GET http://localhost:4000/api/users/camera-permission/999999999
```

**Expected Response (404):**
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

### Test 10: Invalid Endpoint (404)

```bash
curl -X GET http://localhost:4000/api/invalid-endpoint
```

**Expected Response (404):**
```json
{
  "success": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "Route not found"
  }
}
```

---

> **On the removed 404 branch:** `POST /api/users/camera-permission` no longer
> has a "record to update not found" 404. It uses `upsert` (create-or-update),
> so a missing record is created rather than erroring — that branch was
> unreachable and has been removed. The **only** 404 for permissions is on the
> `GET` above (Test 9).
>
> **Foreign key note:** posting a permission for a `userId` that does not exist
> in the `User` table fails the FK constraint and returns a `500 DATABASE_ERROR`.
> Always create the user first (see the flow below).

---

## 🎯 Valid Permission Status Values

| Value | Description |
|-------|-------------|
| `"granted"` | User granted camera permission |
| `"denied"` | User denied camera permission |
| `"prompted"` | User has been prompted but not yet decided (default) |

---

## 🚀 Full Flow (zero → user → permission → read back)

```bash
API=http://localhost:4000

# 0. Server up?
curl "$API/health"

# 1. Create a user (capture the integer id)
USER_ID=$(curl -s -X POST "$API/api/users" \
  -H "Content-Type: application/json" \
  -d '{"email":"flow@example.com","name":"Flow User"}' \
  | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)
echo "userId = $USER_ID"

# 2. Set the camera permission for that user
curl -X POST "$API/api/users/camera-permission" \
  -H "Content-Type: application/json" \
  -d "{\"userId\":$USER_ID,\"status\":\"granted\"}"

# 3. Read the permission back
curl "$API/api/users/camera-permission/$USER_ID"
```

---

## 📊 Pretty-Print with jq

```bash
curl -s http://localhost:4000/api/users/camera-permission/1 | jq '.'
```
