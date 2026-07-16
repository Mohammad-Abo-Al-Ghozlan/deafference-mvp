#!/bin/bash

# Deafference API - Testing Script
# Exercises every endpoint and every documented response against the real
# (integer-keyed) API contract.
#
# Prerequisites:
#   1. A migrated database (see README: `npx prisma migrate dev`)
#   2. The API running:  `npm run server:dev`   (listens on http://localhost:4000)

API_BASE_URL="http://localhost:4000"
CONTENT_TYPE="application/json"

# Unique email per run so the "create user" test always returns 201, and so the
# script stays re-runnable against a persistent database.
EMAIL="test-$(date +%s)-$RANDOM@example.com"

echo "🧪 Deafference API - Test Suite"
echo "========================================"
echo ""

# Test 1: Health Check (expect 200)
echo "✅ Test 1: Health Check"
echo "Command: GET /health"
curl -s -X GET "$API_BASE_URL/health" \
  -H "Content-Type: $CONTENT_TYPE" \
  -w "\n\n"

# Test 2: Create User (expect 201) — capture the generated integer id
echo "✅ Test 2: Create User"
echo "Command: POST /api/users"
CREATE_RESP=$(curl -s -X POST "$API_BASE_URL/api/users" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{"email":"'"$EMAIL"'","name":"Test User"}')
echo "$CREATE_RESP"
USER_ID=$(echo "$CREATE_RESP" | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)
echo ""
echo "-> captured userId: $USER_ID"
echo ""

# Test 3: Duplicate email (expect 409)
echo "❌ Test 3: Duplicate User (Should Fail - 409)"
echo "Command: POST /api/users (same email)"
curl -s -X POST "$API_BASE_URL/api/users" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{"email":"'"$EMAIL"'"}' \
  -w "\n\n"

# Test 4: Create Camera Permission (upsert, expect 200)
echo "✅ Test 4: Create Camera Permission (Upsert)"
echo "Command: POST /api/users/camera-permission"
curl -s -X POST "$API_BASE_URL/api/users/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{"userId":'"$USER_ID"',"status":"granted"}' \
  -w "\n\n"

# Test 5: Retrieve Permission (expect 200)
echo "✅ Test 5: Retrieve Permission"
echo "Command: GET /api/users/camera-permission/$USER_ID"
curl -s -X GET "$API_BASE_URL/api/users/camera-permission/$USER_ID" \
  -H "Content-Type: $CONTENT_TYPE" \
  -w "\n\n"

# Test 6: Update Permission (upsert, status -> denied, expect 200)
echo "✅ Test 6: Update Permission (Status Changed to denied)"
echo "Command: POST /api/users/camera-permission"
curl -s -X POST "$API_BASE_URL/api/users/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{"userId":'"$USER_ID"',"status":"denied"}' \
  -w "\n\n"

# Test 7: Invalid Status (expect 400)
echo "❌ Test 7: Invalid Status (Should Fail - 400)"
echo "Command: POST /api/users/camera-permission with invalid status"
curl -s -X POST "$API_BASE_URL/api/users/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{"userId":'"$USER_ID"',"status":"invalid_status"}' \
  -w "\n\n"

# Test 8: Missing userId (expect 400)
echo "❌ Test 8: Missing userId (Should Fail - 400)"
echo "Command: POST /api/users/camera-permission without userId"
curl -s -X POST "$API_BASE_URL/api/users/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{"status":"granted"}' \
  -w "\n\n"

# Test 9: Missing status (expect 400)
echo "❌ Test 9: Missing status (Should Fail - 400)"
echo "Command: POST /api/users/camera-permission without status"
curl -s -X POST "$API_BASE_URL/api/users/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{"userId":'"$USER_ID"'}' \
  -w "\n\n"

# Test 10: Create User without email (expect 400)
echo "❌ Test 10: Create User Missing email (Should Fail - 400)"
echo "Command: POST /api/users without email"
curl -s -X POST "$API_BASE_URL/api/users" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{"name":"No Email"}' \
  -w "\n\n"

# Test 11: GET permission with non-integer userId (expect 400)
echo "❌ Test 11: GET Permission with non-integer userId (Should Fail - 400)"
echo "Command: GET /api/users/camera-permission/not-a-number"
curl -s -X GET "$API_BASE_URL/api/users/camera-permission/not-a-number" \
  -H "Content-Type: $CONTENT_TYPE" \
  -w "\n\n"

# Test 12: Get Non-Existent Permission (expect 404)
echo "❌ Test 12: Get Non-Existent Permission (Should Fail - 404)"
echo "Command: GET /api/users/camera-permission/999999999"
curl -s -X GET "$API_BASE_URL/api/users/camera-permission/999999999" \
  -H "Content-Type: $CONTENT_TYPE" \
  -w "\n\n"

# Test 13: Invalid Endpoint (expect 404)
echo "❌ Test 13: Invalid Endpoint (Should Fail - 404)"
echo "Command: GET /api/invalid-endpoint"
curl -s -X GET "$API_BASE_URL/api/invalid-endpoint" \
  -H "Content-Type: $CONTENT_TYPE" \
  -w "\n\n"

echo ""
echo "✨ Test suite completed!"
