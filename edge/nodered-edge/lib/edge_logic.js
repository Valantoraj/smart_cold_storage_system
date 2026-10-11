'use strict';
/**
 * edge_logic.js — Edge validation and flagging logic
 * ====================================================
 * Implements spec 3.4: validate raw samples, flag spikes and hard limits.
 * Pure functions + an LRU-style dedupe cache per unit.
 * 100% unit-testable without Node-RED.
 */

const VALID_UNITS  = new Set(['CS-01', 'CS-02', 'CS-03']);
const CLOCK_SKEW_S = 300;   // 5 minutes
const SPIKE_THRESH = 3.0;   // °C change per sample
const DEDUP_TTL_MS = 600000; // 10 minutes

// In-memory state (one instance per Node-RED process)
const _lastTemp  = {};   // unit_id → last accepted temp_c
const _seenKeys  = {};   // unit_id → Map<ts, expiry>

function _pruneDedup(unitId) {
    const map = _seenKeys[unitId];
    if (!map) return;
    const now = Date.now();
    for (const [key, expiry] of map.entries()) {
        if (expiry < now) map.delete(key);
    }
}

/**
 * validate(rawJson, nowMs, units)
 * @param {object} raw         - parsed raw sample (schema 3.3)
 * @param {number} nowMs       - current wall clock (ms since epoch)
 * @param {object} [units]     - optional units config override
 * @returns {{ ok: boolean, reason: string|null, sample: object|null,
 *             flags: string[], edgeAlert: boolean }}
 */
function validate(raw, nowMs, units) {
    const unitsCfg = units || {
        'CS-01': { hard_limit_c: 8.0 },
        'CS-02': { hard_limit_c: 8.0 },
        'CS-03': { hard_limit_c: 8.0 },
    };

    // Schema check
    if (!raw || raw.schema !== 'v1') {
        return _reject('INVALID_SCHEMA');
    }

    // Required fields
    const required = ['unit_id', 'ts', 'seq', 'temp_c',
                      'humidity_pct', 'compressor_on', 'power_kw'];
    for (const f of required) {
        if (!(f in raw)) return _reject('MISSING_FIELD:' + f);
    }

    // Unit ID
    if (!VALID_UNITS.has(raw.unit_id)) {
        return _reject('UNKNOWN_UNIT:' + raw.unit_id);
    }

    // Type checks
    if (typeof raw.temp_c       !== 'number') return _reject('TYPE_temp_c');
    if (typeof raw.humidity_pct !== 'number') return _reject('TYPE_humidity_pct');
    if (typeof raw.power_kw     !== 'number') return _reject('TYPE_power_kw');
    if (typeof raw.compressor_on !== 'boolean') return _reject('TYPE_compressor_on');

    // Range checks
    if (raw.temp_c       < -40 || raw.temp_c       > 40)  return _reject('RANGE_temp_c');
    if (raw.humidity_pct <   0 || raw.humidity_pct > 100) return _reject('RANGE_humidity_pct');
    if (raw.power_kw     <   0 || raw.power_kw     > 50)  return _reject('RANGE_power_kw');

    // Timestamp parse and clock skew
    let sampleMs;
    try {
        sampleMs = new Date(raw.ts).getTime();
        if (isNaN(sampleMs)) throw new Error('NaN');
    } catch (_) {
        return _reject('INVALID_TS');
    }
    if (Math.abs(sampleMs - nowMs) > CLOCK_SKEW_S * 1000) {
        return _reject('CLOCK_SKEW');
    }

    // Deduplicate by (unit_id, ts)
    const uid = raw.unit_id;
    if (!_seenKeys[uid]) _seenKeys[uid] = new Map();
    _pruneDedup(uid);
    const key = raw.ts;
    if (_seenKeys[uid].has(key)) {
        return _reject('DUPLICATE');
    }
    _seenKeys[uid].set(key, nowMs + DEDUP_TTL_MS);

    // Build validated sample
    const flags     = [];
    let   suspect   = false;
    let   edgeAlert = false;

    // Spike detection
    const prevTemp = _lastTemp[uid];
    if (prevTemp !== undefined && Math.abs(raw.temp_c - prevTemp) > SPIKE_THRESH) {
        flags.push('SPIKE');
        suspect = true;
    }
    _lastTemp[uid] = raw.temp_c;

    // Hard limit
    const cfg = unitsCfg[uid] || {};
    if (raw.temp_c > (cfg.hard_limit_c || 8.0)) {
        flags.push('HARD_LIMIT');
        edgeAlert = true;
    }

    const edgeTs = new Date(nowMs).toISOString();
    const sample = Object.assign({}, raw, {
        edge_node: process.env.EDGE_NODE_ID || 'edge-l1',
        edge_ts:   edgeTs,
        suspect,
        flags,
    });

    return { ok: true, reason: null, sample, flags, edgeAlert };
}

function _reject(reason) {
    return { ok: false, reason, sample: null, flags: [], edgeAlert: false };
}

module.exports = { validate };
