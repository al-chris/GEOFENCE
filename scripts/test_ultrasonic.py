#!/usr/bin/env python3
"""
test_ultrasonic.py
Standalone test script for the front HC-SR04 ultrasonic sensor on Raspberry Pi 5.

Uses lgpio for Pi 5 compatibility (RPi.GPIO does not support the RP1 chip).

Wiring (see WIRING.md):
    VCC  -> 5V  (Pin 2 or 4)
    GND  -> GND (Pin 6)
    TRIG -> GPIO 23 (Pin 16)
    ECHO -> GPIO 24 (Pin 18)  <- MUST go through the 1k/2k voltage divider!

The HC-SR04 ECHO pin outputs 5V. The Pi 5 GPIO pins are 3.3V-only inputs, so a
1 kOhm / 2 kOhm divider (ECHO -> 1k -> node -> 2k -> GND) is mandatory.

Usage:
    python3 scripts/test_ultrasonic.py [--chip 4] [--trig 23] [--echo 24]
"""

import argparse
import time
from typing import Optional

import lgpio

# --- CONFIGURATION ---
GPIO_CHIP = 4   # Pi 5 RP1 header - verify with `gpiodetect`
TRIG_PIN = 23
ECHO_PIN = 24

TEMPERATURE_C = 20.0        # used for the speed-of-sound correction
ECHO_TIMEOUT_S = 0.03       # ~5 m round trip; also stops us hanging on a dead sensor
MAX_DISTANCE_CM = 400.0


def setup(chip: int, trig: int, echo: int) -> int:
    print(f"Opening gpiochip{chip}...")
    try:
        h = lgpio.gpiochip_open(chip)
        print(f"Opened handle: {h}")
    except Exception as e:
        print(f"Failed to open gpiochip{chip}. Run 'gpiodetect' to verify your chip number!")
        raise e

    # You MUST claim all pins before using them in lgpio
    lgpio.gpio_claim_output(h, trig, 0)
    lgpio.gpio_claim_input(h, echo)
    print(f"Claimed TRIG GPIO{trig} (output) and ECHO GPIO{echo} (input).")
    return h


def measure_cm(h: int, trig: int, echo: int,
               temperature_c: float = TEMPERATURE_C,
               timeout: float = ECHO_TIMEOUT_S) -> Optional[float]:
    """Trigger one ping and return the distance in cm, or None on timeout."""
    # 10 microsecond trigger pulse
    lgpio.gpio_write(h, trig, 1)
    time.sleep(0.00001)
    lgpio.gpio_write(h, trig, 0)

    # Wait for ECHO to go HIGH (start of the return pulse)
    t0 = time.perf_counter()
    while lgpio.gpio_read(h, echo) == 0:
        if time.perf_counter() - t0 > timeout:
            return None
    pulse_start = time.perf_counter()

    # Wait for ECHO to go LOW again (end of the return pulse)
    while lgpio.gpio_read(h, echo) == 1:
        if time.perf_counter() - pulse_start > timeout:
            return None
    pulse_end = time.perf_counter()

    duration_s = pulse_end - pulse_start
    speed_of_sound_m_s = 331.3 + 0.606 * temperature_c
    distance_cm = (duration_s * speed_of_sound_m_s * 100.0) / 2.0

    if distance_cm <= 0 or distance_cm > MAX_DISTANCE_CM:
        return None
    return round(distance_cm, 1)


def parse_args():
    p = argparse.ArgumentParser(description="HC-SR04 ultrasonic test utility for Raspberry Pi 5 (lgpio)")
    p.add_argument("--chip", type=int, default=GPIO_CHIP,
                   help="gpiochip number (default 4 on the Pi 5 header)")
    p.add_argument("--trig", type=int, default=TRIG_PIN, help="TRIG pin (BCM)")
    p.add_argument("--echo", type=int, default=ECHO_PIN, help="ECHO pin (BCM)")
    p.add_argument("--seconds", type=float, default=20.0, help="how long to sample (default 20s)")
    return p.parse_args()


def main():
    args = parse_args()
    h = None
    try:
        h = setup(args.chip, args.trig, args.echo)
        print("Starting HC-SR04 test - wave your hand in front of the sensor.")
        print("Press Ctrl+C to stop.\n")

        end = time.time() + args.seconds
        while time.time() < end:
            distance = measure_cm(h, args.trig, args.echo)
            text = "out of range / no echo" if distance is None else f"{distance:6.1f} cm"
            print(f"{text}   ", end="\r", flush=True)
            time.sleep(0.1)
        print("\nDone.")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if h is not None:
            try:
                lgpio.gpio_free(h, args.trig)
                lgpio.gpio_free(h, args.echo)
                lgpio.gpiochip_close(h)
                print("GPIO cleaned up.")
            except Exception as cleanup_err:
                print(f"Cleanup error (safe to ignore): {cleanup_err}")


if __name__ == "__main__":
    main()
