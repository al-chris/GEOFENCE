#!/usr/bin/env python3
"""
test_motors.py
Standalone test script for the GEOFENCE BTS7960 motor drivers on Raspberry Pi 5.
Ramps both drive motors forward and backward.

Uses lgpio for Pi 5 compatibility (RPi.GPIO does not support the RP1 chip).

IMPORTANT: Check your chip number by running `gpiodetect` in the terminal!
Look for the chip labelled "pinctrl-rp1" / "rp1". On this Pi 5 Ubuntu setup
that chip was gpiochip4.

Usage:
    python3 scripts/test_motors.py [--chip 4] [--motor left|right|both]
"""

import argparse
import time

import lgpio

# --- CONFIGURATION ---
GPIO_CHIP = 4   # Pi 5 RP1 header - verify with `gpiodetect`

# Pin definitions (BCM) - see WIRING.md
MOTORS = {
    # name: (rpwm, lpwm, r_en, l_en)
    "left":  (12, 13, 20, 21),
    "right": (18, 19, 16, 26),
}

# 1000 Hz is stable for DC motors.
FREQ = 1000
# Speeds below this are treated as a stop (motor dead-band).
DEAD_BAND = 5


def setup(chip: int, motors: dict) -> int:
    print(f"Opening gpiochip{chip}...")
    try:
        h = lgpio.gpiochip_open(chip)
        print(f"Opened handle: {h}")
    except Exception as e:
        print(f"Failed to open gpiochip{chip}. Run 'gpiodetect' to verify your chip number!")
        raise e

    print("Claiming output pins...")
    # You MUST claim all pins as outputs before using them in lgpio
    for name, (rpwm, lpwm, r_en, l_en) in motors.items():
        lgpio.gpio_claim_output(h, r_en, 0)
        lgpio.gpio_claim_output(h, l_en, 0)
        lgpio.gpio_claim_output(h, rpwm, 0)
        lgpio.gpio_claim_output(h, lpwm, 0)

    print("Writing enables HIGH...")
    for _, (_, _, r_en, l_en) in motors.items():
        lgpio.gpio_write(h, r_en, 1)
        lgpio.gpio_write(h, l_en, 1)

    print("Initializing PWM to 0...")
    for _, (rpwm, lpwm, _, _) in motors.items():
        lgpio.tx_pwm(h, rpwm, FREQ, 0)
        lgpio.tx_pwm(h, lpwm, FREQ, 0)

    print("Setup complete.")
    return h


def set_motor(h: int, pins: tuple, speed: int):
    """
    Control one BTS7960 motor.
    speed: -100 (full reverse) to 100 (full forward)
    """
    rpwm, lpwm, _, _ = pins
    duty_cycle = abs(speed)

    if speed >= DEAD_BAND:
        # Forward
        lgpio.tx_pwm(h, lpwm, FREQ, 0)
        lgpio.tx_pwm(h, rpwm, FREQ, duty_cycle)
    elif speed <= -DEAD_BAND:
        # Reverse
        lgpio.tx_pwm(h, rpwm, FREQ, 0)
        lgpio.tx_pwm(h, lpwm, FREQ, duty_cycle)
    else:
        # Stop
        lgpio.tx_pwm(h, rpwm, FREQ, 0)
        lgpio.tx_pwm(h, lpwm, FREQ, 0)


def set_all_motors(h: int, motors: dict, speed: int):
    for pins in motors.values():
        set_motor(h, pins, speed)


def ramp_motors(h: int, motors: dict, direction: int = 1):
    """direction: 1 for forward, -1 for reverse"""
    label = "FORWARD" if direction > 0 else "REVERSE"
    print(f"--- Ramping {label} ---")

    # Ramp up
    for s in range(0, 101, 5):
        set_all_motors(h, motors, s * direction)
        # Trailing spaces overwrite leftover characters from '100%'
        print(f"Speed: {s}%   ", end="\r", flush=True)
        time.sleep(0.1)

    time.sleep(1)

    # Ramp down
    for s in range(100, -1, -5):
        set_all_motors(h, motors, s * direction)
        print(f"Speed: {s}%   ", end="\r", flush=True)
        time.sleep(0.1)
    print("\nDone.")


def parse_args():
    p = argparse.ArgumentParser(description="BTS7960 motor test utility for Raspberry Pi 5 (lgpio)")
    p.add_argument("--chip", type=int, default=GPIO_CHIP,
                   help="gpiochip number (default 4 on the Pi 5 header)")
    p.add_argument("--motor", choices=["left", "right", "both"], default="both",
                   help="which motor(s) to test (default: both)")
    return p.parse_args()


def main():
    args = parse_args()
    motors = MOTORS if args.motor == "both" else {args.motor: MOTORS[args.motor]}

    h = None
    try:
        h = setup(args.chip, motors)
        print(f"Starting BTS7960 Motor Test (Pi 5 - lgpio) - {args.motor} motor(s)")
        print("Make sure the robot is on blocks / wheels are free to spin!")
        time.sleep(2)

        # Forward
        ramp_motors(h, motors, 1)
        time.sleep(1)

        # Reverse
        ramp_motors(h, motors, -1)
        time.sleep(1)

        print("Test complete.")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if h is not None:
            # Safely shut everything down
            try:
                for _, (rpwm, lpwm, r_en, l_en) in motors.items():
                    lgpio.tx_pwm(h, rpwm, FREQ, 0)
                    lgpio.tx_pwm(h, lpwm, FREQ, 0)
                    lgpio.gpio_write(h, r_en, 0)
                    lgpio.gpio_write(h, l_en, 0)
                    lgpio.gpio_free(h, rpwm)
                    lgpio.gpio_free(h, lpwm)
                    lgpio.gpio_free(h, r_en)
                    lgpio.gpio_free(h, l_en)
                lgpio.gpiochip_close(h)
                print("GPIO cleaned up.")
            except Exception as cleanup_err:
                print(f"Cleanup error (safe to ignore): {cleanup_err}")


if __name__ == "__main__":
    main()
