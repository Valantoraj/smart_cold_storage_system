#!/usr/bin/env python3
"""
Smart Cold Storage - Continuous Sensor Simulator

Starts all three cold storage units with realistic scenarios and
sends data to the MQTT broker indefinitely (until Ctrl+C).

Usage:
    python run_continuous.py
    python run_continuous.py --mqtt-host localhost --interval 60
    python run_continuous.py --scenario normal    # all units normal
    python run_continuous.py --scenario mixed     # realistic mixed (default)
    python run_continuous.py --scenario stress    # all units with issues

Environment variable override:
    MQTT_HOST   - MQTT broker host  (default: localhost)
    MQTT_PORT   - MQTT broker port  (default: 1883)
    INTERVAL    - Seconds between readings (default: 60)
"""

import os
import argparse
import signal
import sys
from sensor_simulator import SensorSimulator


def handle_signal(sig, frame):
    print("\n\nStopping continuous simulator...")
    sys.exit(0)


# Graceful shutdown on Ctrl+C or SIGTERM
signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


# ─── Preset configurations ─────────────────────────────────────────────────

PRESETS = {
    # All units operating normally – baseline / demo
    "normal": [
        ("CS-01", "normal"),
        ("CS-02", "normal"),
        ("CS-03", "normal"),
    ],

    # Realistic mixed state: one normal, one degrading, one with high energy
    # Good for demonstrating predictive maintenance and condition alerts
    "mixed": [
        ("CS-01", "normal"),
        ("CS-02", "equipment_degradation"),
        ("CS-03", "high_energy"),
    ],

    # All units under stress – triggers multiple alert types quickly
    "stress": [
        ("CS-01", "temp_rising"),
        ("CS-02", "humidity_issue"),
        ("CS-03", "equipment_degradation"),
    ],

    # Failure scenarios – demonstrates critical alerts
    "failure": [
        ("CS-01", "door_open"),
        ("CS-02", "compressor_failure"),
        ("CS-03", "normal"),
    ],
}


def main():
    parser = argparse.ArgumentParser(
        description="Continuous sensor simulator for Smart Cold Storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Presets:
  normal   All units in normal operation
  mixed    CS-01 normal, CS-02 degrading, CS-03 high energy (default)
  stress   All units with developing issues
  failure  Two units in critical failure state

Examples:
  python run_continuous.py
  python run_continuous.py --scenario stress --interval 30
  python run_continuous.py --mqtt-host 192.168.1.100
        """
    )

    parser.add_argument(
        "--mqtt-host",
        default=os.environ.get("MQTT_HOST", "localhost"),
        help="MQTT broker host (default: localhost or $MQTT_HOST)"
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=int(os.environ.get("MQTT_PORT", 1883)),
        help="MQTT broker port (default: 1883 or $MQTT_PORT)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("INTERVAL", 60)),
        help="Seconds between readings per unit (default: 60)"
    )
    parser.add_argument(
        "--scenario",
        choices=list(PRESETS.keys()),
        default="mixed",
        help="Preset scenario to run (default: mixed)"
    )

    args = parser.parse_args()

    # ── Print startup banner ────────────────────────────────────────────────
    print("=" * 65)
    print("  Smart Cold Storage - Continuous Sensor Simulator")
    print("=" * 65)
    print(f"  MQTT Broker : {args.mqtt_host}:{args.mqtt_port}")
    print(f"  Interval    : every {args.interval} seconds per unit")
    print(f"  Scenario    : {args.scenario}")
    print(f"  Duration    : continuous (Ctrl+C to stop)")
    print("=" * 65)
    print()

    units = PRESETS[args.scenario]
    for unit_id, scenario in units:
        print(f"  Unit {unit_id}  →  scenario: {scenario}")
    print()

    # ── Build and run simulator ─────────────────────────────────────────────
    simulator = SensorSimulator(args.mqtt_host, args.mqtt_port)

    for unit_id, scenario in units:
        simulator.add_unit(unit_id, scenario)

    # duration=None → runs indefinitely
    simulator.run(interval=args.interval, duration=None)


if __name__ == "__main__":
    main()
