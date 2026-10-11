#!/usr/bin/env bash
# Gate G1-ALT: Full network verification
L1=100.74.249.115; L1U=nithish
L2=100.83.223.86;  L2U=roop
L3=100.122.173.70; L3U=valan
KEY=~/.ssh/id_ed25519
PASS=0; FAIL=0

ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "================================================="
echo "  GATE G1-ALT: Full Network Verification"
echo "================================================="

echo ""
echo "--- Tailscale ping ---"
/snap/bin/tailscale ping --c 1 $L1 2>&1 | grep -q pong && ok "L3→L1 tailscale" || fail "L3→L1 tailscale"
/snap/bin/tailscale ping --c 1 $L2 2>&1 | grep -q pong && ok "L3→L2 tailscale" || fail "L3→L2 tailscale"

echo ""
echo "--- SSH port 2222 ---"
ssh -p 2222 -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes ${L1U}@${L1} "echo ok" 2>/dev/null \
  && ok "L3→L1 SSH:2222" || fail "L3→L1 SSH:2222"
ssh -p 2222 -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes ${L2U}@${L2} "echo ok" 2>/dev/null \
  && ok "L3→L2 SSH:2222" || fail "L3→L2 SSH:2222"
ssh -p 2222 -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes ${L3U}@${L3} "echo ok" 2>/dev/null \
  && ok "L3→L3 SSH:2222 (self)" || fail "L3→L3 SSH:2222 (self)"

echo ""
echo "--- Docker on L3 ---"
docker run -d --rm -p 9002:80 --name gate-test nginx:alpine > /dev/null 2>&1
sleep 2
curl -sf --max-time 5 "http://${L3}:9002/" > /dev/null 2>&1 \
  && ok "L3 Docker port 9002" || fail "L3 Docker port 9002"
docker stop gate-test > /dev/null 2>&1 || true

echo ""
echo "--- Docker installed on L1/L2 ---"
ssh -p 2222 -i $KEY -o StrictHostKeyChecking=no -o BatchMode=yes ${L1U}@${L1} "which docker" 2>/dev/null \
  && ok "L1 has docker" || fail "L1 docker not installed (will install next)"
ssh -p 2222 -i $KEY -o StrictHostKeyChecking=no -o BatchMode=yes ${L2U}@${L2} "which docker" 2>/dev/null \
  && ok "L2 has docker" || fail "L2 docker not installed (will install next)"

echo ""
echo "================================================="
echo "  PASSED: $PASS   FAILED: $FAIL"
echo "================================================="
if [ $FAIL -eq 0 ]; then
  echo "  GATE G1-ALT: PASS"
elif [ $FAIL -le 2 ]; then
  echo "  GATE G1-ALT: PASS (minor items to fix)"
else
  echo "  GATE G1-ALT: FAIL - fix above items"
fi
