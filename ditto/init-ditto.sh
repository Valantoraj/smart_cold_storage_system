#!/bin/bash
# Initialize Eclipse Ditto Digital Twins
# This script creates the policy and things for all cold storage units

DITTO_URL="http://localhost:8080/api/2"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "Initializing Eclipse Ditto Digital Twins"
echo "========================================"
echo ""

# Wait for Ditto to be ready
echo "Waiting for Ditto to be ready..."
until curl -s -f -o /dev/null "${DITTO_URL%/api/2}/health"; do
  echo "  Ditto not ready yet, waiting..."
  sleep 5
done
echo "✓ Ditto is ready"
echo ""

# Create policy
echo "Creating cold-storage-policy..."
POLICY_RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT "${DITTO_URL}/policies/org.eclipse.ditto:cold-storage-policy" \
  -H "Content-Type: application/json" \
  -d @"${SCRIPT_DIR}/policies/cold-storage-policy.json")

HTTP_CODE=$(echo "$POLICY_RESPONSE" | tail -n1)
if [ "$HTTP_CODE" -eq 201 ] || [ "$HTTP_CODE" -eq 204 ]; then
  echo "✓ Policy created successfully"
else
  echo "✗ Failed to create policy (HTTP $HTTP_CODE)"
  echo "Response: $(echo "$POLICY_RESPONSE" | head -n-1)"
fi
echo ""

# Create things
UNITS=("CS-01" "CS-02" "CS-03")

for unit in "${UNITS[@]}"; do
  echo "Creating thing ${unit}..."
  THING_RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT "${DITTO_URL}/things/org.eclipse.ditto:${unit}" \
    -H "Content-Type: application/json" \
    -d @"${SCRIPT_DIR}/things/${unit}.json")
  
  HTTP_CODE=$(echo "$THING_RESPONSE" | tail -n1)
  if [ "$HTTP_CODE" -eq 201 ] || [ "$HTTP_CODE" -eq 204 ]; then
    echo "✓ Thing ${unit} created successfully"
  else
    echo "✗ Failed to create thing ${unit} (HTTP $HTTP_CODE)"
    echo "Response: $(echo "$THING_RESPONSE" | head -n-1)"
  fi
  echo ""
done

echo "========================================"
echo "Initialization complete!"
echo "========================================"
echo ""
echo "Verify by running:"
echo "  curl ${DITTO_URL}/things"
echo ""
echo "Get specific thing:"
echo "  curl ${DITTO_URL}/things/org.eclipse.ditto:CS-01"
echo ""
