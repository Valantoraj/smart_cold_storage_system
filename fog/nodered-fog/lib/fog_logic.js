'use strict';
/**
 * fog_logic.js — Fog windowed features and PM rule engine
 * ========================================================
 * Computes 1-minute aggregates and 15-minute windowed features per unit.
 * Implements the health state machine and PM_WARNING rule from spec 3.5.
 */

const DEFAULT_RULES = {
    window_min:             15,
    warmup_min:             15,
    eval_interval_s:        60,
    baseline_duty:          0.40,
    pm: {
        slope_c_per_min:    0.03,
        duty_ratio:         1.30,
        on_power_ratio:     1.10,
        consecutive_evals:  3,
    },
    temp_critical:          { over_hard_limit_min: 2 },
    humidity:               { out_of_range_min: 5 },
    clear_evals_to_deescalate: 5,
    renotify_min:           10,
    late_data_max_min:      30,
    stale_alert_suppress_min: 2,
    ewma:                   { alpha: 0.05, k_sigma: 4.0 },
};

const DEFAULT_UNITS = {
    'CS-01': { setpoint_c: 4.0, hard_limit_c: 8.0, humidity_range: [55, 85] },
    'CS-02': { setpoint_c: 4.0, hard_limit_c: 8.0, humidity_range: [55, 85] },
    'CS-03': { setpoint_c: 5.0, hard_limit_c: 8.0, humidity_range: [55, 85] },
};

// Per-unit running state
const _unitState = {};

function _getState(uid, rules, units) {
    if (!_unitState[uid]) {
        _unitState[uid] = {
            samples:        [],      // raw samples buffer (last window_min minutes)
            buckets:        [],      // 1-min buckets [{ts,temp_avg,duty,power_avg,on_power}]
            healthState:    'OK',
            healthScore:    100,
            pmConsec:       0,       // consecutive PM evals
            critConsec:     0,       // consecutive critical temp evals
            humConsec:      0,       // consecutive humidity breach evals
            clearConsec:    0,       // consecutive clear evals
            baselinePower:  null,    // learned baseline on-power
            baselineDuty:   rules.baseline_duty,
            startedAt:      Date.now(),
            lastAlertMs:    {},      // code → last fire time
            ewma_mean:      null,
            ewma_var:       0.0,
            lastEvalMs:     0,
        };
    }
    return _unitState[uid];
}

/**
 * ingest(sample, nowMs, rules, units)
 * Add a validated sample to the per-unit buffer.
 */
function ingest(sample, nowMs, rules, units) {
    rules = rules || DEFAULT_RULES;
    units = units || DEFAULT_UNITS;
    const uid   = sample.unit_id;
    const state = _getState(uid, rules, units);
    const windowMs = (rules.window_min || 15) * 60 * 1000;

    // Append sample
    state.samples.push({ ...sample, _arrivedMs: nowMs });

    // Prune old samples
    const cutoff = nowMs - windowMs;
    state.samples = state.samples.filter(s => {
        const sMs = new Date(s.ts).getTime();
        return sMs >= cutoff;
    });
}

/**
 * evaluate(uid, nowMs, rules, units)
 * Compute 1-min features + run PM rule. Returns evaluation result.
 */
function evaluate(uid, nowMs, rules, units) {
    rules = rules || DEFAULT_RULES;
    units = units || DEFAULT_UNITS;
    const state   = _getState(uid, rules, units);
    const cfg     = units[uid] || DEFAULT_UNITS['CS-01'];
    const warmupMs = (rules.warmup_min || 15) * 60 * 1000;

    // Still warming up
    if (nowMs - state.startedAt < warmupMs) {
        return { uid, warmup: true, healthState: state.healthState, features: null };
    }

    // Build 1-min bucket for current minute
    const bucketCutMs = nowMs - 60000;
    const recent = state.samples.filter(s => new Date(s.ts).getTime() >= bucketCutMs);

    if (recent.length === 0) {
        return { uid, warmup: false, healthState: state.healthState, features: null, noData: true };
    }

    const temps     = recent.map(s => s.temp_c).filter(v => v != null);
    const powers    = recent.map(s => s.power_kw).filter(v => v != null);
    const onPowers  = recent.filter(s => s.compressor_on).map(s => s.power_kw).filter(v => v != null);
    const dutyCount = recent.filter(s => s.compressor_on).length;
    const duty      = dutyCount / recent.length;
    const tempAvg   = _avg(temps);
    const powerAvg  = _avg(powers);
    const onPowerAvg = onPowers.length > 0 ? _avg(onPowers) : null;

    // Temp slope (least-squares over window)
    const windowSamples = state.samples.slice(-60); // last 60 points
    const slope = _lsSlope(windowSamples);

    // EWMA update
    const alpha = (rules.ewma || {}).alpha || 0.05;
    if (state.ewma_mean === null) {
        state.ewma_mean = tempAvg;
    } else {
        const residual = tempAvg - state.ewma_mean;
        state.ewma_var  = (1 - alpha) * (state.ewma_var + alpha * residual * residual);
        state.ewma_mean = state.ewma_mean + alpha * residual;
    }

    // Store bucket
    const bucket = { ts: new Date(nowMs).toISOString(), tempAvg, duty, powerAvg, onPowerAvg, slope };
    state.buckets.push(bucket);
    if (state.buckets.length > rules.window_min * 2) state.buckets.shift();

    // Baseline on-power learning (only when OK)
    if (state.healthState === 'OK' && onPowerAvg !== null) {
        if (state.baselinePower === null) {
            state.baselinePower = onPowerAvg;
        } else {
            state.baselinePower = state.baselinePower * 0.99 + onPowerAvg * 0.01;
        }
    }
    const basePower = state.baselinePower || 2.0;
    const baseDuty  = state.baselineDuty  || 0.40;

    // ── PM Rule ──────────────────────────────────────────────────────────────
    const pm = rules.pm || {};
    const pmCondSlope = (slope !== null) && slope >= (pm.slope_c_per_min || 0.03);
    const pmCondDuty  = duty >= baseDuty * (pm.duty_ratio || 1.30);
    const pmCondPower = onPowerAvg !== null && onPowerAvg >= basePower * (pm.on_power_ratio || 1.10);
    const pmFired = pmCondSlope && pmCondDuty && pmCondPower;

    if (pmFired) {
        state.pmConsec++;
    } else {
        state.pmConsec = 0;
    }
    const pmWarning = state.pmConsec >= (pm.consecutive_evals || 3);

    // ── CRITICAL temp ────────────────────────────────────────────────────────
    const hardLimit = cfg.hard_limit_c || 8.0;
    const overLimit = tempAvg > hardLimit;
    if (overLimit) state.critConsec++; else state.critConsec = 0;
    const tempCritical = state.critConsec >= ((rules.temp_critical || {}).over_hard_limit_min || 2);

    // ── Humidity ─────────────────────────────────────────────────────────────
    const [humLo, humHi] = cfg.humidity_range || [55, 85];
    const humOOR = recent.filter(s => s.humidity_pct < humLo || s.humidity_pct > humHi).length;
    const humBreach = humOOR / recent.length > 0.5;
    if (humBreach) state.humConsec++; else state.humConsec = 0;
    const humAlert = state.humConsec >= ((rules.humidity || {}).out_of_range_min || 5);

    // ── Health state machine ──────────────────────────────────────────────────
    const triggers = [];
    if (tempCritical) triggers.push('TEMP_CRITICAL');
    if (pmWarning)    triggers.push('PM_WARNING');
    if (humAlert)     triggers.push('HUMIDITY_OUT_OF_RANGE');

    let newState = state.healthState;
    if (tempCritical) {
        newState = 'CRITICAL';
        state.clearConsec = 0;
    } else if (pmWarning || humAlert) {
        if (newState === 'OK') newState = 'WARNING';
        state.clearConsec = 0;
    } else {
        if (newState !== 'OK') {
            state.clearConsec++;
            if (state.clearConsec >= (rules.clear_evals_to_deescalate || 5)) {
                newState = 'OK';
                state.clearConsec = 0;
                state.pmConsec    = 0;
                state.critConsec  = 0;
                state.humConsec   = 0;
            }
        }
    }

    // Health score
    let score = 100;
    if (pmWarning)    score -= 30;
    if (tempCritical) score -= 40;
    if (humAlert)     score -= 10;
    score = Math.max(0, score);

    const stateChanged = newState !== state.healthState;
    state.healthState = newState;
    state.healthScore = score;

    const features = {
        temp_avg_c:            round(tempAvg, 3),
        temp_min_c:            round(Math.min(...temps), 3),
        temp_max_c:            round(Math.max(...temps), 3),
        humidity_avg_pct:      round(_avg(recent.map(s => s.humidity_pct)), 2),
        compressor_duty:       round(duty, 4),
        power_avg_kw:          round(powerAvg, 3),
        on_power_avg_kw:       onPowerAvg !== null ? round(onPowerAvg, 3) : null,
        temp_slope_c_per_min:  slope !== null ? round(slope, 5) : null,
        sample_count:          recent.length,
    };

    return {
        uid,
        warmup:       false,
        healthState:  newState,
        healthScore:  score,
        features,
        triggers,
        stateChanged,
        pmWarning,
        tempCritical,
        humAlert,
    };
}

// ── Math helpers ─────────────────────────────────────────────────────────────

function _avg(arr) {
    if (!arr || arr.length === 0) return 0;
    return arr.reduce((a, b) => a + b, 0) / arr.length;
}

function _lsSlope(samples) {
    if (samples.length < 2) return null;
    const pts = samples
        .map(s => ({ t: new Date(s.ts).getTime() / 60000, v: s.temp_c }))
        .filter(p => !isNaN(p.v));
    if (pts.length < 2) return null;
    const n   = pts.length;
    const tBar = _avg(pts.map(p => p.t));
    const vBar = _avg(pts.map(p => p.v));
    const num   = pts.reduce((s, p) => s + (p.t - tBar) * (p.v - vBar), 0);
    const denom = pts.reduce((s, p) => s + (p.t - tBar) ** 2, 0);
    return denom === 0 ? 0 : num / denom;
}

function round(v, d) {
    if (v == null) return null;
    return Math.round(v * 10 ** d) / 10 ** d;
}

module.exports = { ingest, evaluate };
