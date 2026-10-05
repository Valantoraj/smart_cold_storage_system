#!/bin/bash
# Smart Cold Storage Digital Twin - REST API Test Script
# Tests all REST API endpoints with cURL

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
API_BASE_URL="http://localhost:3001/api"
PASSED=0
FAILED=0

# Helper functions
print_section() {
    echo -e "\n${CYAN}=== $1 ===${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
    ((PASSED++))
}

print_failure() {
    echo -e "${RED}✗ $1${NC}"
    ((FAILED++))
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

test_endpoint() {
    local name="$1"
    local url="$2"
    local expected_status="${3:-200}"
    
    echo -n "Testing $name... "
    
    response=$(curl -s -w "\n%{http_code}" "$url" 2>/dev/null)
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "$expected_status" ]; then
        print_success "$name (HTTP $http_code)"
        if [ "$VERBOSE" = "true" ]; then
            echo "$body" | jq '.' 2>/dev/null || echo "$body"
        fi
        return 0
    else
        print_failure "$name (Expected $expected_status, got $http_code)"
        if [ "$VERBOSE" = "true" ]; then
            echo "$body"
        fi
        return 1
    fi
}

# =============================================================================
# Main Test Execution
# =============================================================================

echo ""
echo "======================================================================"
echo "  Smart Cold Storage Digital Twin - REST API Tests"
echo "======================================================================"
echo ""

# =============================================================================
# 1. Health Check
# =============================================================================

print_section "Health Check"

test_endpoint "API Health" "$API_BASE_URL/health"

# =============================================================================
# 2. Storage Units Endpoints
# =============================================================================

print_section "Storage Units"

test_endpoint "List all storage units" "$API_BASE_URL/storage"
test_endpoint "Get unit CS-01" "$API_BASE_URL/storage/CS-01"
test_endpoint "Get unit CS-02" "$API_BASE_URL/storage/CS-02"
test_endpoint "Get unit CS-03" "$API_BASE_URL/storage/CS-03"
test_endpoint "Get non-existent unit (should 404)" "$API_BASE_URL/storage/CS-99" 404

# =============================================================================
# 3. Current Data Endpoints
# =============================================================================

print_section "Current Sensor Data"

test_endpoint "Current data CS-01" "$API_BASE_URL/storage/CS-01/current"
test_endpoint "Current data CS-02" "$API_BASE_URL/storage/CS-02/current"
test_endpoint "Current data CS-03" "$API_BASE_URL/storage/CS-03/current"

# =============================================================================
# 4. Historical Data Endpoints
# =============================================================================

print_section "Historical Data"

test_endpoint "History CS-01 (default)" "$API_BASE_URL/storage/CS-01/history"
test_endpoint "History CS-01 (last 1 hour)" "$API_BASE_URL/storage/CS-01/history?start=-1h"
test_endpoint "History CS-01 (last 6 hours)" "$API_BASE_URL/storage/CS-01/history?start=-6h"
test_endpoint "History CS-01 (temp only)" "$API_BASE_URL/storage/CS-01/history?fields=temperature"
test_endpoint "History CS-01 (temp and energy)" "$API_BASE_URL/storage/CS-01/history?fields=temperature,energyConsumption"

# =============================================================================
# 5. Alerts Endpoints
# =============================================================================

print_section "Alerts"

test_endpoint "All alerts" "$API_BASE_URL/alerts"
test_endpoint "Active alerts" "$API_BASE_URL/alerts?status=active"
test_endpoint "Critical alerts" "$API_BASE_URL/alerts?severity=critical"
test_endpoint "Alerts for CS-01" "$API_BASE_URL/storage/CS-01/alerts"
test_endpoint "Last hour alerts" "$API_BASE_URL/alerts?start=-1h"

# =============================================================================
# 6. Maintenance Endpoints
# =============================================================================

print_section "Predictive Maintenance"

test_endpoint "All maintenance scores" "$API_BASE_URL/maintenance/scores"
test_endpoint "Maintenance CS-01" "$API_BASE_URL/storage/CS-01/maintenance"
test_endpoint "Maintenance CS-02" "$API_BASE_URL/storage/CS-02/maintenance"
test_endpoint "Maintenance CS-03" "$API_BASE_URL/storage/CS-03/maintenance"

# =============================================================================
# 7. Analytics Endpoints
# =============================================================================

print_section "Analytics"

test_endpoint "Analytics summary (default)" "$API_BASE_URL/analytics/summary"
test_endpoint "Analytics summary (1 hour)" "$API_BASE_URL/analytics/summary?start=-1h"
test_endpoint "Analytics summary (7 days)" "$API_BASE_URL/analytics/summary?start=-7d"

# =============================================================================
# 8. Digital Twins Endpoints
# =============================================================================

print_section "Digital Twins"

test_endpoint "List all digital twins" "$API_BASE_URL/twins"
test_endpoint "Get twin CS-01" "$API_BASE_URL/twins/org.eclipse.ditto:CS-01"
test_endpoint "Get twin CS-02" "$API_BASE_URL/twins/org.eclipse.ditto:CS-02"
test_endpoint "Get twin CS-03" "$API_BASE_URL/twins/org.eclipse.ditto:CS-03"

# =============================================================================
# 9. Error Handling
# =============================================================================

print_section "Error Handling"

test_endpoint "404 endpoint" "$API_BASE_URL/nonexistent" 404
test_endpoint "404 storage unit" "$API_BASE_URL/storage/INVALID" 404

# =============================================================================
# 10. Response Format Validation
# =============================================================================

print_section "Response Format Validation"

echo -n "Validating JSON response format... "
response=$(curl -s "$API_BASE_URL/storage")
if echo "$response" | jq '.' > /dev/null 2>&1; then
    print_success "Valid JSON response"
else
    print_failure "Invalid JSON response"
fi

echo -n "Checking storage list has count field... "
if echo "$response" | jq -e '.count' > /dev/null 2>&1; then
    print_success "Count field present"
else
    print_failure "Count field missing"
fi

echo -n "Checking storage list has units array... "
if echo "$response" | jq -e '.units | type == "array"' > /dev/null 2>&1; then
    print_success "Units array present"
else
    print_failure "Units array missing"
fi

# =============================================================================
# Test Summary
# =============================================================================

echo ""
echo "======================================================================"
echo "  Test Summary"
echo "======================================================================"
echo ""

TOTAL=$((PASSED + FAILED))
if [ $TOTAL -gt 0 ]; then
    PASS_RATE=$(echo "scale=1; ($PASSED / $TOTAL) * 100" | bc)
else
    PASS_RATE=0
fi

echo "Total Tests:    $TOTAL"
echo -e "Passed:         ${GREEN}$PASSED ($PASS_RATE%)${NC}"
echo -e "Failed:         ${RED}$FAILED${NC}"

echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All API tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some API tests failed. Please review the output above.${NC}"
    exit 1
fi
