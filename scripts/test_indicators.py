#!/usr/bin/env python3
"""
test_indicators.py
Standalone test script for the geofence buzzer and status LEDs on Raspberry Pi 5.

Uses lgpio for Pi 5 compatibility (RPi.GPIO does not support the RP1 chip).

Wiring (see WIRING.md):
    Buzzer     +  -> GPIO 17 (Pin 11)     high = sound
    Red LED    +  -> GPIO 27 (Pin 13)     via 220 Ohm to GND
    Green LED  +  -> GPIO 22 (Pin 15)     via 220 Ohm to GND

These are the same pins the geofence_node uses by default, so a pass here means
the boundary indicators will work on hardware.

Usage:
    python3 scripts/test_indicators.py [--chip 4] [--cycles 3]
"""

import argparse
import time

import lgpio

# --- CONFIGURATION ---
GPIO_CHIP = 4   # Pi 5 RP1 header - verify with `gpiodetect`

BUZZER_PIN = 17
RED_LED_PIN = 27
GREEN_LED_PIN = 22


def setup(chip: int, pins: tuple) -> int:
    print(f"Opening gpiochip{chip}...")
    try:
        h = lgpio.gpiochip_open(chip)
        print(f"Opened handle: {h}")
    except Exception as e:
        print(f"Failed to open gpiochip{chip}. Run 'gpiodetect' to verify your chip number!")
        raise e

    print("Claiming output pins...")
    # You MUST claim all pins as outputs before using them in lgpio
    for pin in pins:
        lgpio.gpio_claim_output(h, pin, 0)
    return h


def all_off(h: int, pins: tuple):
    for pin in pins:
        lgpio.gpio_write(h, pin, 0)


def parse_args():
    p = argparse.ArgumentParser(description="Buzzer / status LED test utility for Raspberry Pi 5 (lgpio)")
    p.add_argument("--chip", type=int, default=GPIO_CHIP,
                   help="gpiochip number (default 4 on the Pi 5 header)")
    p.add_argument("--cycles", type=int, default=3, help="number of test cycles (default 3)")
    return p.parse_args()


def main():
    args = parse_args()
    pins = (BUZZER_PIN, RED_LED_PIN, GREEN_LED_PIN)
    h = None
    try:
        h = setup(args.chip, pins)
        print("Starting indicator test (buzzer + LEDs, lgpio)...")
        print("Sequence per cycle: GREEN (inside) -> RED + BUZZER (breach) -> all off\n")
        time.sleep(1)

        for cycle in range(1, args.cycles + 1):
            print(f"--- Cycle {cycle}/{args.cycles} ---")

            all_off(h, pins)
            time.sleep(0.3)

            lgpio.gpio_write(h, GREEN_LED_PIN, 1)
            print("GREEN LED on (inside boundary)")
            time.sleep(1.0)

            lgpio.gpio_write(h, GREEN_LED_PIN, 0)
            lgpio.gpio_write(h, RED_LED_PIN, 1)
            lgpio.gpio_write(h, BUZZER_PIN, 1)
            print("RED LED + BUZZER on (boundary crossed)")

            # Buzzer pulses so it is obvious which output is which
            for _ in range(3):
                lgpio.gpio_write(h, BUZZER_PIN, 0)
                time.sleep(0.15)
                lgpio.gpio_write(h, BUZZER_PIN, 1)
                time.sleep(0.35)

            all_off(h, pins)
            print("All indicators off")
            time.sleep(0.5)

        print("\nTest complete.")

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if h is not None:
            try:
                all_off(h, pins)
                for pin in pins:
                    lgpio.gpio_free(h, pin)
                lgpio.gpiochip_close(h)
                print("GPIO cleaned up.")
            except Exception as cleanup_err:
                print(f"Cleanup error (safe to ignore): {cleanup_err}")


if __name__ == "__main__":
    main()
