#!/usr/bin/env python3
"""
Smart Cold Storage Sensor Simulator

This simulator generates realistic sensor data for cold storage units,
including both normal operation and various abnormal scenarios for testing
the digital twin system's monitoring and predictive maintenance capabilities.
"""

import json
import time
import random
import argparse
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import List, Dict
import paho.mqtt.client as mqtt


@dataclass
class SensorReading:
    """Data class for sensor readings"""
    unitId: str
    temperature: float
    humidity: float
    compressorStatus: str
    energyConsumption: float
    timestamp: str


class ColdStorageUnit:
    """Simulates a cold storage unit with realistic behavior"""
    
    def __init__(self, unit_id: str, scenario: str = "normal"):
        self.unit_id = unit_id
        self.scenario = scenario
        
        # Normal operating parameters
        self.target_temp = 4.0
        self.target_humidity = 65.0
        self.base_energy = 2.0
        
        # Current state
        self.temperature = self.target_temp
        self.humidity = self.target_humidity
        self.compressor_on = False
        self.compressor_runtime = 0
        self.compressor_cycles = 0
        self.energy_consumption = 0.0
        
        # Scenario-specific parameters
        self.scenario_step = 0
        self.scenario_params = self._init_scenario()
        
    def _init_scenario(self) -> Dict:
        """Initialize scenario-specific parameters"""
        scenarios = {
            "normal": {
                "temp_variance": 0.2,
                "humidity_variance": 2.0,
                "energy_variance": 0.1,
                "compressor_cycle_time": 600  # 10 minutes
            },
            "temp_rising": {
                "temp_increase_rate": 0.05,  # Per reading
                "humidity_variance": 2.0,
                "energy_increase_rate": 0.02,
                "compressor_cycle_time": 500
            },
            "temp_fluctuating": {
                "temp_variance": 1.0,
                "humidity_variance": 3.0,
                "energy_variance": 0.3,
                "compressor_cycle_time": 300  # Short cycles
            },
            "high_energy": {
                "temp_variance": 0.3,
                "humidity_variance": 2.0,
                "energy_increase_rate": 0.03,
                "base_energy_multiplier": 1.5,
                "compressor_cycle_time": 600
            },
            "humidity_issue": {
                "temp_variance": 0.2,
                "humidity_drift_rate": 0.5,
                "energy_variance": 0.1,
                "compressor_cycle_time": 600
            },
            "equipment_degradation": {
                "temp_increase_rate": 0.03,
                "humidity_variance": 2.5,
                "energy_increase_rate": 0.025,
                "compressor_cycle_time": 450,
                "efficiency_degradation": True
            },
            "door_open": {
                "temp_increase_rate": 0.15,
                "humidity_increase_rate": 1.0,
                "energy_increase_rate": 0.05,
                "compressor_cycle_time": 400
            },
            "compressor_failure": {
                "temp_increase_rate": 0.08,
                "compressor_stuck_off": True,
                "energy_consumption_zero": True
            }
        }
        return scenarios.get(self.scenario, scenarios["normal"])
    
    def simulate_reading(self) -> SensorReading:
        """Generate a sensor reading based on current state and scenario"""
        self.scenario_step += 1
        
        # Update temperature based on scenario
        if self.scenario == "normal":
            self._simulate_normal_temp()
        elif self.scenario == "temp_rising":
            self._simulate_rising_temp()
        elif self.scenario == "temp_fluctuating":
            self._simulate_fluctuating_temp()
        elif self.scenario == "high_energy":
            self._simulate_high_energy()
        elif self.scenario == "humidity_issue":
            self._simulate_humidity_issue()
        elif self.scenario == "equipment_degradation":
            self._simulate_equipment_degradation()
        elif self.scenario == "door_open":
            self._simulate_door_open()
        elif self.scenario == "compressor_failure":
            self._simulate_compressor_failure()
        
        # Update compressor state
        self._update_compressor()
        
        # Calculate energy consumption
        self._calculate_energy()
        
        # Create and return reading
        return SensorReading(
            unitId=self.unit_id,
            temperature=round(self.temperature, 2),
            humidity=round(self.humidity, 1),
            compressorStatus="ON" if self.compressor_on else "OFF",
            energyConsumption=round(self.energy_consumption, 2),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    
    def _simulate_normal_temp(self):
        """Normal operation with minor fluctuations"""
        variance = self.scenario_params["temp_variance"]
        
        # Temperature drifts slightly and compressor brings it back
        if self.compressor_on:
            # Cooling when compressor is on
            self.temperature -= random.uniform(0.05, 0.15)
        else:
            # Warming when compressor is off
            self.temperature += random.uniform(0.02, 0.08)
        
        # Add small random variation
        self.temperature += random.uniform(-variance, variance)
        
        # Keep within reasonable bounds
        self.temperature = max(2.0, min(6.0, self.temperature))
        
        # Humidity stays stable
        self.humidity += random.uniform(-2.0, 2.0)
        self.humidity = max(60, min(70, self.humidity))
    
    def _simulate_rising_temp(self):
        """Temperature gradually rising (cooling problem)"""
        rate = self.scenario_params["temp_increase_rate"]
        
        # Steady increase
        self.temperature += rate + random.uniform(-0.01, 0.02)
        
        # Compressor struggles to cool
        if self.compressor_on:
            self.temperature -= 0.03  # Less effective
        
        # Humidity slightly increases too
        self.humidity += random.uniform(-1.0, 2.0)
        self.humidity = max(60, min(75, self.humidity))
    
    def _simulate_fluctuating_temp(self):
        """Temperature fluctuating wildly (control issue)"""
        variance = self.scenario_params["temp_variance"]
        
        # Large swings
        self.temperature += random.uniform(-variance, variance)
        
        # Compressor cycles too frequently
        if self.scenario_step % 5 == 0:
            self.compressor_on = not self.compressor_on
        
        self.humidity += random.uniform(-3.0, 3.0)
        self.humidity = max(55, min(75, self.humidity))
    
    def _simulate_high_energy(self):
        """Normal temperature but high energy consumption"""
        # Temperature normal
        self._simulate_normal_temp()
        
        # Energy will be increased in _calculate_energy
        pass
    
    def _simulate_humidity_issue(self):
        """Humidity drifting out of range"""
        # Temperature mostly normal
        variance = self.scenario_params["temp_variance"]
        self.temperature += random.uniform(-variance, variance)
        
        if self.compressor_on:
            self.temperature -= 0.08
        else:
            self.temperature += 0.05
        
        self.temperature = max(3.0, min(5.5, self.temperature))
        
        # Humidity drifting up
        drift_rate = self.scenario_params["humidity_drift_rate"]
        self.humidity += drift_rate + random.uniform(-1.0, 1.0)
        self.humidity = min(85, self.humidity)
    
    def _simulate_equipment_degradation(self):
        """Multiple signs of equipment degradation"""
        # Temperature slowly rising
        rate = self.scenario_params["temp_increase_rate"]
        self.temperature += rate
        
        if self.compressor_on:
            self.temperature -= 0.05  # Less effective cooling
        else:
            self.temperature += 0.06
        
        # Humidity less stable
        self.humidity += random.uniform(-2.5, 2.5)
        self.humidity = max(62, min(72, self.humidity))
        
        # Energy will increase in _calculate_energy
    
    def _simulate_door_open(self):
        """Door left open - rapid temperature and humidity increase"""
        rate_temp = self.scenario_params["temp_increase_rate"]
        rate_humidity = self.scenario_params["humidity_increase_rate"]
        
        # Rapid increase
        self.temperature += rate_temp + random.uniform(0, 0.05)
        self.humidity += rate_humidity + random.uniform(0, 0.5)
        
        # Compressor runs continuously but can't keep up
        self.compressor_on = True
        
        # Bounds
        self.temperature = min(15.0, self.temperature)
        self.humidity = min(90, self.humidity)
    
    def _simulate_compressor_failure(self):
        """Compressor failed - not running"""
        # Temperature rises steadily
        rate = self.scenario_params["temp_increase_rate"]
        self.temperature += rate + random.uniform(0, 0.02)
        
        # Compressor stuck off
        self.compressor_on = False
        
        # Humidity increases
        self.humidity += random.uniform(0.5, 1.5)
        self.humidity = min(85, self.humidity)
        
        # Energy near zero
        self.energy_consumption = random.uniform(0.1, 0.3)
    
    def _update_compressor(self):
        """Update compressor state based on temperature"""
        if self.scenario == "compressor_failure":
            self.compressor_on = False
            return
        
        if self.scenario == "door_open":
            self.compressor_on = True
            return
        
        cycle_time = self.scenario_params.get("compressor_cycle_time", 600)
        
        # Simple thermostat logic
        if self.temperature > self.target_temp + 0.5:
            if not self.compressor_on:
                self.compressor_on = True
                self.compressor_cycles += 1
        elif self.temperature < self.target_temp - 0.3:
            self.compressor_on = False
        
        # Track runtime
        if self.compressor_on:
            self.compressor_runtime += 1
    
    def _calculate_energy(self):
        """Calculate energy consumption"""
        if self.scenario == "compressor_failure":
            self.energy_consumption = random.uniform(0.1, 0.3)
            return
        
        base = self.base_energy
        
        # Apply multiplier for high energy scenario
        if self.scenario == "high_energy":
            base *= self.scenario_params.get("base_energy_multiplier", 1.5)
        
        if self.compressor_on:
            # Base energy when running
            self.energy_consumption = base + random.uniform(0.3, 0.7)
            
            # Increase with scenario progression for degradation
            if self.scenario in ["equipment_degradation", "temp_rising", "high_energy"]:
                rate = self.scenario_params.get("energy_increase_rate", 0.02)
                increase = self.scenario_step * rate
                self.energy_consumption += increase
            
            # Higher energy when struggling
            if self.temperature > self.target_temp + 1.0:
                self.energy_consumption += 0.5
        else:
            # Standby energy
            self.energy_consumption = random.uniform(0.1, 0.3)
        
        # Cap at reasonable maximum
        self.energy_consumption = min(5.0, self.energy_consumption)


class SensorSimulator:
    """Main simulator managing multiple units"""
    
    def __init__(self, mqtt_host: str = "localhost", mqtt_port: int = 1883):
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.client = None
        self.units: List[ColdStorageUnit] = []
        self.running = False
        
    def add_unit(self, unit_id: str, scenario: str = "normal"):
        """Add a cold storage unit to simulate"""
        unit = ColdStorageUnit(unit_id, scenario)
        self.units.append(unit)
        print(f"Added unit {unit_id} with scenario '{scenario}'")
        
    def connect_mqtt(self):
        """Connect to MQTT broker"""
        self.client = mqtt.Client(client_id="sensor_simulator")
        
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                print(f"Connected to MQTT broker at {self.mqtt_host}:{self.mqtt_port}")
            else:
                print(f"Failed to connect to MQTT broker, return code {rc}")
        
        def on_disconnect(client, userdata, rc):
            if rc != 0:
                print(f"Unexpected disconnection from MQTT broker")
        
        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        
        try:
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.client.loop_start()
            time.sleep(1)  # Wait for connection
        except Exception as e:
            print(f"Error connecting to MQTT broker: {e}")
            raise
    
    def publish_reading(self, reading: SensorReading):
        """Publish a sensor reading to MQTT"""
        topic = f"coldstorage/{reading.unitId}/data"
        payload = json.dumps(asdict(reading))
        
        result = self.client.publish(topic, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[{reading.timestamp}] {reading.unitId}: "
                  f"Temp={reading.temperature}°C, "
                  f"Humidity={reading.humidity}%, "
                  f"Compressor={reading.compressorStatus}, "
                  f"Energy={reading.energyConsumption}kW")
        else:
            print(f"Failed to publish to {topic}")
    
    def run(self, interval: int = 60, duration: int = None):
        """Run the simulator"""
        self.running = True
        self.connect_mqtt()
        
        start_time = time.time()
        iteration = 0
        
        print(f"\n{'='*80}")
        print(f"Starting simulation with {len(self.units)} units")
        print(f"Publishing interval: {interval} seconds")
        if duration:
            print(f"Duration: {duration} seconds")
        print(f"{'='*80}\n")
        
        try:
            while self.running:
                iteration += 1
                print(f"\n--- Iteration {iteration} ---")
                
                # Generate and publish readings for all units
                for unit in self.units:
                    reading = unit.simulate_reading()
                    self.publish_reading(reading)
                
                # Check duration
                if duration and (time.time() - start_time) >= duration:
                    print(f"\nSimulation duration reached ({duration}s)")
                    break
                
                # Wait for next iteration
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\nSimulation stopped by user")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the simulator"""
        self.running = False
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        print("\nSimulator stopped")


def main():
    parser = argparse.ArgumentParser(
        description="Smart Cold Storage Sensor Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scenarios:
  normal                : Normal operation with minor fluctuations
  temp_rising          : Temperature gradually rising (cooling problem)
  temp_fluctuating     : Temperature fluctuating wildly (control issue)
  high_energy          : Normal temperature but high energy consumption
  humidity_issue       : Humidity drifting out of acceptable range
  equipment_degradation: Multiple signs of equipment degradation
  door_open            : Door left open scenario
  compressor_failure   : Compressor failure (not running)

Examples:
  # Run with default settings (3 normal units)
  python sensor_simulator.py
  
  # Custom units and scenarios
  python sensor_simulator.py --units CS-01:normal CS-02:temp_rising CS-03:high_energy
  
  # Faster updates for testing
  python sensor_simulator.py --interval 10
  
  # Run for specific duration
  python sensor_simulator.py --duration 600
  
  # Connect to remote MQTT broker
  python sensor_simulator.py --mqtt-host 192.168.1.100 --mqtt-port 1883
        """
    )
    
    parser.add_argument(
        "--mqtt-host",
        default="localhost",
        help="MQTT broker hostname (default: localhost)"
    )
    
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=1883,
        help="MQTT broker port (default: 1883)"
    )
    
    parser.add_argument(
        "--units",
        nargs="+",
        default=["CS-01:normal", "CS-02:normal", "CS-03:normal"],
        help="Units to simulate in format UNIT_ID:SCENARIO (default: CS-01:normal CS-02:normal CS-03:normal)"
    )
    
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval between readings in seconds (default: 60)"
    )
    
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Total simulation duration in seconds (default: infinite)"
    )
    
    args = parser.parse_args()
    
    # Create simulator
    simulator = SensorSimulator(args.mqtt_host, args.mqtt_port)
    
    # Add units
    for unit_spec in args.units:
        if ":" in unit_spec:
            unit_id, scenario = unit_spec.split(":", 1)
        else:
            unit_id = unit_spec
            scenario = "normal"
        
        simulator.add_unit(unit_id, scenario)
    
    # Run simulation
    simulator.run(interval=args.interval, duration=args.duration)


if __name__ == "__main__":
    main()
