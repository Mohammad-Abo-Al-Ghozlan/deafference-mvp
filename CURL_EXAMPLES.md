# Camera Permission API - cURL Testing Examples

## Prerequisites

- API server running on `http://localhost:3000`
- `curl` command available in terminal
- jq (optional, for pretty-printing JSON)

---

## 🔍 Quick Test Commands

### 1. Health Check

```bash
curl -X GET http://localhost:3000/health
```

**Expected Response (200):**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "environment": "development"
}
```

---

### 2. Create Camera Permission (New User)

```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-12345",
    "status": "granted",
    "updatedAt": "2024-01-15T10:30:00Z"
  }'
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "id": "clq1a2b3c4d5e6f7g8h9i0j1",
    "userId": "user-12345",
    "status": "granted",
    "updatedAt": "2024-01-15T10:30:00.000Z",
    "createdAt": "2024-01-15T10:30:00.123Z"
  }
}
```

---

### 3. Update Permission (Upsert - Status Changed)

```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-12345",
    "status": "denied",
    "updatedAt": "2024-01-15T11:00:00Z"
  }'
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "id": "clq1a2b3c4d5e6f7g8h9i0j1",
    "userId": "user-12345",
    "status": "denied",
    "updatedAt": "2024-01-15T11:00:00.000Z",
    "createdAt": "2024-01-15T10:30:00.123Z"
  }
}
```

**Note:** `createdAt` remains unchanged, but `updatedAt` reflects the new timestamp.

---

### 4. Get User's Permission

```bash
curl -X GET http://localhost:3000/api/users/user-12345/camera-permission
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "id": "clq1a2b3c4d5e6f7g8h9i0j1",
    "userId": "user-12345",
    "status": "denied",
    "updatedAt": "2024-01-15T11:00:00.000Z",
    "createdAt": "2024-01-15T10:30:00.123Z"
  }
}
```

---

### 5. Create Permission with Different Status

```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-67890",
    "status": "dismissed",
    "updatedAt": "2024-01-15T09:15:00Z"
  }'
```

**Expected Response (200):**
```json
{
  "success": true,
  "data": {
    "id": "clq2b3c4d5e6f7g8h9i0j1k2",
    "userId": "user-67890",
    "status": "dismissed",
    "updatedAt": "2024-01-15T09:15:00.000Z",
    "createdAt": "2024-01-15T10:31:00.456Z"
  }
}
```

---

## ❌ Error Test Cases

### Test 1: Invalid Status (400 Validation Error)

```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-12345",
    "status": "invalid_value",
    "updatedAt": "2024-01-15T10:30:00Z"
  }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed"
  }
}
```

---

### Test 2: Missing Required Field - userId (400)

```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "status": "granted",
    "updatedAt": "2024-01-15T10:30:00Z"
  }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed"
  }
}
```

---

### Test 3: Missing Required Field - status (400)

```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-12345",
    "updatedAt": "2024-01-15T10:30:00Z"
  }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed"
  }
}
```

---

### Test 4: Missing Required Field - updatedAt (400)

```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-12345",
    "status": "granted"
  }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed"
  }
}
```

---

### Test 5: Invalid Date Format (400)

```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-12345",
    "status": "granted",
    "updatedAt": "not-a-valid-date"
  }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed"
  }
}
```

---

### Test 6: Future Date (400)

```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "user-12345",
    "status": "granted",
    "updatedAt": "2099-12-31T23:59:59Z"
  }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed"
  }
}
```

---

### Test 7: Empty userId (400)

```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "",
    "status": "granted",
    "updatedAt": "2024-01-15T10:30:00Z"
  }'
```

**Expected Response (400):**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed"
  }
}
```

---

### Test 8: Get Non-Existent User (404)

```bash
curl -X GET http://localhost:3000/api/users/non-existent-user-xyz/camera-permission
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

### Test 9: Get with Empty userId (400)

```bash
curl -X GET http://localhost:3000/api/users//camera-permission
```

This will result in a routing issue. Expected: **404 Not Found**

---

### Test 10: Invalid Endpoint (404)

```bash
curl -X POST http://localhost:3000/api/users/invalid-endpoint \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Expected Response (404):**
```json
{
  "success": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "Route POST /api/users/invalid-endpoint not found"
  }
}
```

---

## 🎯 Valid Permission Status Values

Only these values are accepted for the `status` field:

| Value | Description |
|-------|-------------|
| `"granted"` | User granted camera permission |
| `"denied"` | User denied camera permission |
| `"dismissed"` | User dismissed the permission prompt |

---

## 📊 Using with Pretty-Print (jq)

If you have `jq` installed, format the response nicely:

```bash
curl -X GET http://localhost:3000/api/users/user-12345/camera-permission | jq '.'
```

**Output:**
```json
{
  "success": true,
  "data": {
    "id": "clq1a2b3c4d5e6f7g8h9i0j1",
    "userId": "user-12345",
    "status": "denied",
    "updatedAt": "2024-01-15T11:00:00.000Z",
    "createdAt": "2024-01-15T10:30:00.123Z"
  }
}
```

---

## 🔧 Advanced cURL Options

### Save Response to File

```bash
curl -X GET http://localhost:3000/api/users/user-12345/camera-permission \
  -o response.json
```

### Show Headers and Body

```bash
curl -X GET http://localhost:3000/api/users/user-12345/camera-permission \
  -i
```

### Measure Response Time

```bash
curl -X GET http://localhost:3000/api/users/user-12345/camera-permission \
  -w "Response time: %{time_total}s\n"
```

### Add Custom Headers

```bash
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: 12345" \
  -d '{
    "userId": "user-12345",
    "status": "granted",
    "updatedAt": "2024-01-15T10:30:00Z"
  }'
```

---

## 📝 Batch Testing with Bash Script

Save this as `test-all.sh` and run `bash test-all.sh`:

```bash
#!/bin/bash

API="http://localhost:3000"

echo "Test 1: Create Permission"
curl -s -X POST "$API/api/users/camera-permission" \
  -H "Content-Type: application/json" \
  -d '{"userId":"user-1","status":"granted","updatedAt":"2024-01-15T10:30:00Z"}' | jq '.'

echo -e "\n\nTest 2: Get Permission"
curl -s -X GET "$API/api/users/user-1/camera-permission" | jq '.'

echo -e "\n\nTest 3: Update Permission"
curl -s -X POST "$API/api/users/camera-permission" \
  -H "Content-Type: application/json" \
  -d '{"userId":"user-1","status":"denied","updatedAt":"2024-01-15T11:00:00Z"}' | jq '.'
```

---

## 🚀 Quick Start Test Sequence

Run these commands in order to test the full flow:

```bash
# 1. Check if server is up
curl http://localhost:3000/health

# 2. Create new permission
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{"userId":"test-user","status":"granted","updatedAt":"2024-01-15T10:30:00Z"}'

# 3. Retrieve the permission
curl http://localhost:3000/api/users/test-user/camera-permission

# 4. Update the permission
curl -X POST http://localhost:3000/api/users/camera-permission \
  -H "Content-Type: application/json" \
  -d '{"userId":"test-user","status":"denied","updatedAt":"2024-01-15T11:00:00Z"}'

# 5. Verify update
curl http://localhost:3000/api/users/test-user/camera-permission
```

---

## 🐛 Troubleshooting

### Connection Refused
- **Issue:** `curl: (7) Failed to connect`
- **Solution:** Ensure server is running: `npm run dev`

### 404 Not Found on Valid Endpoint
- **Issue:** Endpoint returns 404
- **Solution:** Check URL matches exactly (case-sensitive)

### 400 Validation Error
- **Issue:** Request returns validation error
- **Solution:** Check JSON syntax and required fields

### 500 Internal Server Error
- **Issue:** Unexpected server error
- **Solution:** Check server logs, verify database connection

