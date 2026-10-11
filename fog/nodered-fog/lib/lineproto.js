'use strict';
/**
 * lineproto.js — InfluxDB line protocol serialiser
 * =================================================
 * Converts fog aggregate objects to InfluxDB line protocol strings.
 */

/**
 * toLineProtocol(measurement, tags, fields, timestampMs)
 * Returns one line protocol string.
 */
function toLineProtocol(measurement, tags, fields, timestampMs) {
    const tagStr = Object.entries(tags)
        .filter(([, v]) => v != null)
        .map(([k, v]) => `${_escape(k)}=${_escape(String(v))}`)
        .join(',');

    const fieldStr = Object.entries(fields)
        .filter(([, v]) => v != null && v !== '')
        .map(([k, v]) => {
            if (typeof v === 'boolean') return `${_escape(k)}=${v}`;
            if (typeof v === 'string')  return `${_escape(k)}="${v.replace(/"/g, '\\"')}"`;
            return `${_escape(k)}=${v}`;
        })
        .join(',');

    if (!fieldStr) return null;

    const ts = Math.floor(timestampMs) * 1000000; // ms → ns
    return `${_escape(measurement)}${tagStr ? ',' + tagStr : ''} ${fieldStr} ${ts}`;
}

function _escape(s) {
    return String(s).replace(/[ ,=]/g, c => '\\' + c);
}

/**
 * telemetryLine(agg, ts, unitId)
 * Build a line protocol entry for one 1-minute telemetry aggregate.
 */
function telemetryLine(agg, ts, unitId) {
    return toLineProtocol(
        'telemetry',
        { unit_id: unitId },
        {
            temp_avg_c:           agg.temp_avg_c,
            temp_min_c:           agg.temp_min_c,
            temp_max_c:           agg.temp_max_c,
            humidity_avg_pct:     agg.humidity_avg_pct,
            compressor_duty:      agg.compressor_duty,
            power_avg_kw:         agg.power_avg_kw,
            on_power_avg_kw:      agg.on_power_avg_kw,
            temp_slope_c_per_min: agg.temp_slope_c_per_min,
            health_state:         agg.healthState || 'OK',
            health_score:         agg.healthScore || 100,
            sample_count:         agg.sample_count || 0,
        },
        new Date(ts).getTime()
    );
}

/**
 * eventLine(event, ts, unitId)
 */
function eventLine(event, ts, unitId) {
    return toLineProtocol(
        'events',
        { unit_id: unitId, severity: event.severity || 'INFO' },
        { code: event.code, message: event.message || '' },
        new Date(ts).getTime()
    );
}

module.exports = { toLineProtocol, telemetryLine, eventLine };
