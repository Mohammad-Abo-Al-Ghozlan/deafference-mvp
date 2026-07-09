#!/bin/bash

# Camera Permission API - Testing Script
# This script provides cURL commands to test all endpoints

API_BASE_URL="http://localhost:3000"
CONTENT_TYPE="application/json"

echo "🧪 Camera Permission API - Test Suite"
echo "========================================"
echo ""

# Test 1: Health Check
echo "✅ Test 1: Health Check"
echo "Command: GET /health"
curl -X GET "$API_BASE_URL/health" \
  -H "Content-Type: $CONTENT_TYPE" \
  -w "\n\n"

# Test 2: Create New Permission
echo "✅ Test 2: Create New Permission"
echo "Command: POST /api/users/camera-permission"
curl -X POST "$API_BASE_URL/api/users/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{
    "userId": "user-12345",
    "status": "granted",
    "updatedAt": "2024-01-15T10:30:00Z"
  }' \
  -w "\n\n"

# Test 3: Retrieve Permission
echo "✅ Test 3: Retrieve Permission"
echo "Command: GET /api/users/user-12345/camera-permission"
curl -X GET "$API_BASE_URL/api/users/user-12345/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -w "\n\n"

# Test 4: Update Existing Permission (Upsert)
echo "✅ Test 4: Update Permission (Status Changed to Denied)"
echo "Command: POST /api/users/camera-permission"
curl -X POST "$API_BASE_URL/api/users/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{
    "userId": "user-12345",
    "status": "denied",
    "updatedAt": "2024-01-15T11:00:00Z"
  }' \
  -w "\n\n"

# Test 5: Create Another User Permission
echo "✅ Test 5: Create Permission for Another User"
echo "Command: POST /api/users/camera-permission"
curl -X POST "$API_BASE_URL/api/users/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{
    "userId": "user-67890",
    "status": "dismissed",
    "updatedAt": "2024-01-15T09:15:00Z"
  }' \
  -w "\n\n"

# Test 6: Invalid Status (Should Fail - 400)
echo "❌ Test 6: Invalid Status (Should Fail - 400)"
echo "Command: POST /api/users/camera-permission with invalid status"
curl -X POST "$API_BASE_URL/api/users/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{
    "userId": "user-12345",
    "status": "invalid_status",
    "updatedAt": "2024-01-15T10:30:00Z"
  }' \
  -w "\n\n"

# Test 7: Missing Required Field (Should Fail - 400)
echo "❌ Test 7: Missing userId (Should Fail - 400)"
echo "Command: POST /api/users/camera-permission without userId"
curl -X POST "$API_BASE_URL/api/users/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{
    "status": "granted",
    "updatedAt": "2024-01-15T10:30:00Z"
  }' \
  -w "\n\n"

# Test 8: Invalid Date Format (Should Fail - 400)
echo "❌ Test 8: Invalid Date Format (Should Fail - 400)"
echo "Command: POST /api/users/camera-permission with invalid date"
curl -X POST "$API_BASE_URL/api/users/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -d '{
    "userId": "user-12345",
    "status": "granted",
    "updatedAt": "not-a-date"
  }' \
  -w "\n\n"

# Test 9: Get Non-Existent User (Should Return 404)
echo "❌ Test 9: Get Non-Existent User (Should Fail - 404)"
echo "Command: GET /api/users/non-existent-user/camera-permission"
curl -X GET "$API_BASE_URL/api/users/non-existent-user/camera-permission" \
  -H "Content-Type: $CONTENT_TYPE" \
  -w "\n\n"

# Test 10: Invalid Endpoint (Should Return 404)
echo "❌ Test 10: Invalid Endpoint (Should Fail - 404)"
echo "Command: GET /api/invalid-endpoint"
curl -X GET "$API_BASE_URL/api/invalid-endpoint" \
  -H "Content-Type: $CONTENT_TYPE" \
  -w "\n\n"

echo ""
echo "✨ Test suite completed!"
