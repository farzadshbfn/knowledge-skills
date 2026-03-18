// Test KB layout logic — runs with Node.js
// Usage: node test_kb_layout.cjs

const { computeKbLayout } = require("../graph.js");

const EPS = 1e-6;
let passed = 0, failed = 0;

function assert(cond, msg) {
  if (!cond) { console.log("FAIL:", msg); failed++; }
  else { console.log("PASS:", msg); passed++; }
}
function assertNear(a, b, msg) {
  assert(Math.abs(a - b) < EPS, msg + " (got " + a.toFixed(6) + ", expected " + b.toFixed(6) + ")");
}
function angleTo(cx, cy, px, py) { return Math.atan2(py - cy, px - cx); }
function distTo(x1, y1, x2, y2) { return Math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2); }
function normalizeAngle(a) {
  while (a < 0) a += 2 * Math.PI;
  while (a >= 2 * Math.PI) a -= 2 * Math.PI;
  return a;
}
function angleInRange(angle, start, end) {
  angle = normalizeAngle(angle);
  start = normalizeAngle(start);
  end = normalizeAngle(end);
  if (start <= end) return angle >= start - EPS && angle <= end + EPS;
  return angle >= start - EPS || angle <= end + EPS;
}

const W = 1000, H = 1000;
const CX = 500, CY = 500;
const DIM = 1000;
const RING = DIM * 0.3;

// ---- Test 1: Single KB → centered ----
console.log("\n=== Test 1: Single KB centered ===");
{
  const r = computeKbLayout([{ name: "core", path: "./knowledge" }], { core: 10 }, W, H);
  assertNear(r.core.x, CX, "x = center");
  assertNear(r.core.y, CY, "y = center");
}

// ---- Test 2: Core at center, children on ring 1 ----
console.log("\n=== Test 2: Core centered, children on ring 1 ===");
{
  const r = computeKbLayout(
    [
      { name: "core", path: "./knowledge" },
      { name: "eng", path: "./engineering/knowledge" },
      { name: "mkt", path: "./marketing/knowledge" },
    ],
    { core: 50, eng: 30, mkt: 20 }, W, H
  );
  assertNear(r.core.x, CX, "core at center x");
  assertNear(r.core.y, CY, "core at center y");
  assertNear(distTo(r.eng.x, r.eng.y, CX, CY), RING, "eng at ring 1 from center");
  assertNear(distTo(r.mkt.x, r.mkt.y, CX, CY), RING, "mkt at ring 1 from center");
}

// ---- Test 3: Proportional angular allocation ----
console.log("\n=== Test 3: Proportional angles ===");
{
  const r = computeKbLayout(
    [
      { name: "core", path: "./knowledge" },
      { name: "eng", path: "./engineering/knowledge" },
      { name: "mkt", path: "./marketing/knowledge" },
    ],
    { core: 50, eng: 30, mkt: 20 }, W, H
  );
  const angEng = normalizeAngle(angleTo(CX, CY, r.eng.x, r.eng.y));
  const angMkt = normalizeAngle(angleTo(CX, CY, r.mkt.x, r.mkt.y));
  // eng=30, mkt=20 → eng gets 30/50 of 2π, mkt gets 20/50
  const engMid = (30 / 50) * Math.PI; // midpoint of [0, 30/50*2π]
  const mktMid = normalizeAngle((30 / 50) * 2 * Math.PI + (20 / 50) * Math.PI);
  assertNear(angEng, engMid, "eng angle proportional");
  assertNear(angMkt, mktMid, "mkt angle proportional");
}

// ---- Test 4: Children radiate from PARENT, not center ----
console.log("\n=== Test 4: Children radiate from parent ===");
{
  const r = computeKbLayout(
    [
      { name: "core", path: "./knowledge" },
      { name: "eng", path: "./engineering/knowledge" },
      { name: "ios", path: "./engineering/ios/knowledge" },
      { name: "backend", path: "./engineering/backend/knowledge" },
    ],
    { core: 50, eng: 10, ios: 20, backend: 20 }, W, H
  );
  const dIosEng = distTo(r.ios.x, r.ios.y, r.eng.x, r.eng.y);
  const dBackEng = distTo(r.backend.x, r.backend.y, r.eng.x, r.eng.y);
  assertNear(dIosEng, RING, "ios at ring distance from eng");
  assertNear(dBackEng, RING, "backend at ring distance from eng");

  // ios/backend should NOT be at ring 1 from center (they're ring 2)
  const dIosCenter = distTo(r.ios.x, r.ios.y, CX, CY);
  assert(Math.abs(dIosCenter - RING) > 10, "ios NOT at ring 1 from center (dist=" + dIosCenter.toFixed(1) + ")");
}

// ---- Test 5: Children within parent's angular slice (viewed from center) ----
console.log("\n=== Test 5: Children within parent's angular slice ===");
{
  const r = computeKbLayout(
    [
      { name: "core", path: "./knowledge" },
      { name: "eng", path: "./engineering/knowledge" },
      { name: "mkt", path: "./marketing/knowledge" },
      { name: "ios", path: "./engineering/ios/knowledge" },
      { name: "backend", path: "./engineering/backend/knowledge" },
    ],
    { core: 50, eng: 10, mkt: 30, ios: 20, backend: 20 }, W, H
  );
  // eng subtree = 10+20+20=50, mkt=30 → eng gets 50/80 of 2π
  const engEnd = (50 / 80) * 2 * Math.PI;

  const angIos = normalizeAngle(angleTo(CX, CY, r.ios.x, r.ios.y));
  const angBack = normalizeAngle(angleTo(CX, CY, r.backend.x, r.backend.y));
  const angMkt = normalizeAngle(angleTo(CX, CY, r.mkt.x, r.mkt.y));

  assert(angleInRange(angIos, 0, engEnd),
    "ios (" + angIos.toFixed(3) + ") within eng sector [0, " + engEnd.toFixed(3) + "]");
  assert(angleInRange(angBack, 0, engEnd),
    "backend (" + angBack.toFixed(3) + ") within eng sector [0, " + engEnd.toFixed(3) + "]");
  assert(angMkt > engEnd - EPS,
    "mkt (" + angMkt.toFixed(3) + ") outside eng sector (engEnd=" + engEnd.toFixed(3) + ")");
}

// ---- Test 6: Three levels deep ----
console.log("\n=== Test 6: Three levels deep ===");
{
  const r = computeKbLayout(
    [
      { name: "root", path: "./knowledge" },
      { name: "mid", path: "./a/knowledge" },
      { name: "leaf", path: "./a/b/knowledge" },
    ],
    { root: 10, mid: 10, leaf: 10 }, W, H
  );
  assertNear(distTo(r.mid.x, r.mid.y, CX, CY), RING, "mid at ring 1 from center");
  assertNear(distTo(r.leaf.x, r.leaf.y, r.mid.x, r.mid.y), RING, "leaf at ring from mid");

  const dLeafCenter = distTo(r.leaf.x, r.leaf.y, CX, CY);
  const dMidCenter = distTo(r.mid.x, r.mid.y, CX, CY);
  assert(dLeafCenter > dMidCenter + 10, "leaf further from center than mid");
}

// ---- Test 7: Leaf angles within parent sector (from center) ----
console.log("\n=== Test 7: Leaf angles within parent sector ===");
{
  const r = computeKbLayout(
    [
      { name: "root", path: "./knowledge" },
      { name: "a", path: "./a/knowledge" },
      { name: "b", path: "./b/knowledge" },
      { name: "a1", path: "./a/x/knowledge" },
      { name: "a2", path: "./a/y/knowledge" },
    ],
    { root: 10, a: 10, b: 10, a1: 10, a2: 10 }, W, H
  );
  // a subtree=30, b=10 → a gets 30/40 of 2π
  const aEnd = (30 / 40) * 2 * Math.PI;
  const angA1 = normalizeAngle(angleTo(CX, CY, r.a1.x, r.a1.y));
  const angA2 = normalizeAngle(angleTo(CX, CY, r.a2.x, r.a2.y));
  const angB = normalizeAngle(angleTo(CX, CY, r.b.x, r.b.y));

  assert(angleInRange(angA1, 0, aEnd), "a1 within a's sector from center");
  assert(angleInRange(angA2, 0, aEnd), "a2 within a's sector from center");
  assert(angB > aEnd - EPS, "b outside a's sector");
}

console.log("\n=== RESULTS: " + passed + " passed, " + failed + " failed ===");
process.exit(failed > 0 ? 1 : 0);
