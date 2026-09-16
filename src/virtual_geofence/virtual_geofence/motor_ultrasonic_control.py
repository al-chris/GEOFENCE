#!/usr/bin/env python3
"""
motor_ultrasonic_control.py

Standalone rapid hardware testing tool for BTS7960 motor driver(s)
and HC-SR04 ultrasonic distance sensor(s) on Raspberry Pi 5.

USAGE:
    python3 motor_ultrasonic_control.py --mode status         # Read sensors only (safe default)
    python3 motor_ultrasonic_control.py --mode ramp           # Ramp motors fwd/back
    python3 motor_ultrasonic_control.py --mode obstacle       # Drive forward with auto-stop on obstacle
    python3 motor_ultrasonic_control.py --mode obstacle --speed 40 --stop-cm 25
"""

import argparse
import sys
import time

from virtual_geofence.hardware_controller import (
    DEFAULT_GPIO_CHIP,
    DEFAULT_MOTORS,
    DEFAULT_OBSTACLE_STOP_CM,
    DEFAULT_SENSORS,
    RobotController,
)


def mode_status(robot: RobotController, duration_s: float = 20.0):
    """Read-only: prints sensor distances in a loop. Motors are never driven."""
    print(f"--- STATUS MODE (read-only, {duration_s:.0f}s) ---")
    print("Motors will NOT move. Press Ctrl+C to stop early.\n")
    end = time.time() + duration_s
    while time.time() < end:
        readings = robot.read_all_distances()
        line = "  ".join(
            f"{name}: {'--' if dist is None else f'{dist:5.1f} cm'}"
            for name, dist in readings.items()
        )
        print(line, end="\r", flush=True)
        time.sleep(0.1)
    print("\nDone.")


def mode_ramp(robot: RobotController):
    """Ramps all configured motors forward then backward together."""
    print("--- RAMP MODE ---")
    print("Make sure mower wheels are off the ground / on blocks!")
    time.sleep(2)

    for direction, label in ((1, "FORWARD"), (-1, "REVERSE")):
        print(f"\n--- Ramping {label} ---")
        for s in range(0, 101, 5):
            robot.set_all_motors(s * direction)
            print(f"Speed: {s}%   ", end="\r", flush=True)
            time.sleep(0.1)
        time.sleep(1)
        for s in range(100, -1, -5):
            robot.set_all_motors(s * direction)
            print(f"Speed: {s}%   ", end="\r", flush=True)
            time.sleep(0.1)
        robot.stop_all_motors()
        time.sleep(1)
    print("\nRamp test complete.")


def mode_obstacle(robot: RobotController, speed: int, stop_cm: float):
    """
    Drives forward; if ANY sensor sees an obstacle closer than stop_cm,
    stops, briefly reverses, then continues polling.
    """
    print("--- OBSTACLE-AVOIDANCE MODE ---")
    print(f"Base speed: {speed}%   Stop distance: {stop_cm} cm")
    print("Press Ctrl+C to stop.\n")

    if not robot.sensors:
        print("No sensors configured -- nothing to avoid, just driving forward.")

    try:
        while True:
            readings = robot.read_all_distances()
            valid = [d for d in readings.values() if d is not None]
            closest = min(valid) if valid else None

            status = "  ".join(
                f"{name}: {'--' if d is None else f'{d:5.1f} cm'}"
                for name, d in readings.items()
            )

            if closest is not None and closest < stop_cm:
                print(f"{status}  -> OBSTACLE at {closest:.1f} cm, backing off ", end="\r", flush=True)
                robot.stop_all_motors()
                time.sleep(0.2)
                robot.set_all_motors(-speed)
                time.sleep(0.4)
                robot.stop_all_motors()
                time.sleep(0.2)
            else:
                print(f"{status}  -> clear, driving forward     ", end="\r", flush=True)
                robot.set_all_motors(speed)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        robot.stop_all_motors()


def parse_args():
    p = argparse.ArgumentParser(description="BTS7960 + HC-SR04 rapid test utility for Raspberry Pi 5")
    p.add_argument("--mode", choices=["status", "ramp", "obstacle"], default="status",
                   help="status = read sensors only (safe default); ramp = motor speed sweep test; "
                        "obstacle = drive forward with auto-stop on obstacle")
    p.add_argument("--speed", type=int, default=40, help="base speed (0-100) for obstacle mode")
    p.add_argument("--stop-cm", type=float, default=DEFAULT_OBSTACLE_STOP_CM,
                   help="obstacle-stop distance in cm for obstacle mode")
    p.add_argument("--status-seconds", type=float, default=20.0,
                   help="how long to run status mode, in seconds")
    p.add_argument("--chip", type=int, default=DEFAULT_GPIO_CHIP,
                   help="gpiochip number (default 4 on Pi 5)")
    p.add_argument("--mock", action="store_true", help="run with mock hardware")
    return p.parse_args()


def main():
    args = parse_args()
    robot = RobotController(
        motor_configs=DEFAULT_MOTORS,
        sensor_configs=DEFAULT_SENSORS,
        gpio_chip=args.chip,
        mock=args.mock,
    )
    try:
        robot.setup()
        time.sleep(0.5)

        if args.mode == "status":
            mode_status(robot, duration_s=args.status_seconds)
        elif args.mode == "ramp":
            mode_ramp(robot)
        elif args.mode == "obstacle":
            mode_obstacle(robot, speed=args.speed, stop_cm=args.stop_cm)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        robot.cleanup()


if __name__ == "__main__":
    main()
