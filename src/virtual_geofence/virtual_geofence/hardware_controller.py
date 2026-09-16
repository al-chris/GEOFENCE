#!/usr/bin/env python3
"""
hardware_controller.py

Hardware controller for BTS7960 motor driver(s) and HC-SR04 ultrasonic distance sensor(s)
on Raspberry Pi 5 using lgpio. Includes mock fallback for non-Pi / testing environments.
"""

import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    lgpio = None
    LGPIO_AVAILABLE = False


# Default configuration values
DEFAULT_GPIO_CHIP = 4      # Pi 5 rp1 controller
DEFAULT_PWM_FREQ = 1000     # 1000 Hz PWM for BTS7960
DEFAULT_TEMPERATURE_C = 20.0
DEFAULT_ECHO_TIMEOUT_S = 0.03
DEFAULT_SENSOR_SETTLE_S = 0.06
DEFAULT_OBSTACLE_STOP_CM = 20.0


@dataclass
class MotorConfig:
    name: str
    rpwm: int             # forward PWM pin (BCM)
    lpwm: int             # reverse PWM pin (BCM)
    r_en: int             # right-side enable pin (BCM)
    l_en: int             # left-side enable pin (BCM)
    invert: bool = False  # set True if the motor spins backwards


@dataclass
class UltrasonicConfig:
    name: str
    trig: int             # trigger pin (BCM)
    echo: int             # echo pin (BCM) -- through voltage divider to Pi
    max_distance_cm: float = 400.0


# Suggested default pin maps matching WIRING.md
DEFAULT_MOTORS: List[MotorConfig] = [
    MotorConfig(name="left_motor",  rpwm=12, lpwm=13, r_en=20, l_en=21),
    MotorConfig(name="right_motor", rpwm=18, lpwm=19, r_en=16, l_en=26),
]

DEFAULT_SENSORS: List[UltrasonicConfig] = [
    UltrasonicConfig(name="front", trig=23, echo=24),
]


class MotorDriver:
    """Controls one BTS7960 half-bridge motor driver."""

    def __init__(self, handle: Optional[int], cfg: MotorConfig, mock: bool = False):
        self.h = handle
        self.cfg = cfg
        self.mock = mock
        self._speed = 0

    def setup(self):
        if self.mock or not LGPIO_AVAILABLE or self.h is None:
            return
        lgpio.gpio_claim_output(self.h, self.cfg.r_en, 0)
        lgpio.gpio_claim_output(self.h, self.cfg.l_en, 0)
        lgpio.gpio_claim_output(self.h, self.cfg.rpwm, 0)
        lgpio.gpio_claim_output(self.h, self.cfg.lpwm, 0)
        lgpio.gpio_write(self.h, self.cfg.r_en, 1)
        lgpio.gpio_write(self.h, self.cfg.l_en, 1)
        lgpio.tx_pwm(self.h, self.cfg.rpwm, DEFAULT_PWM_FREQ, 0)
        lgpio.tx_pwm(self.h, self.cfg.lpwm, DEFAULT_PWM_FREQ, 0)

    def set_speed(self, speed: int):
        """speed: -100 (full reverse) to 100 (full forward). Dead-band at +-5."""
        speed = max(-100, min(100, speed))
        if self.cfg.invert:
            speed = -speed
        self._speed = speed
        duty = abs(speed)

        if self.mock or not LGPIO_AVAILABLE or self.h is None:
            return

        if speed >= 5:
            lgpio.tx_pwm(self.h, self.cfg.lpwm, DEFAULT_PWM_FREQ, 0)
            lgpio.tx_pwm(self.h, self.cfg.rpwm, DEFAULT_PWM_FREQ, duty)
        elif speed <= -5:
            lgpio.tx_pwm(self.h, self.cfg.rpwm, DEFAULT_PWM_FREQ, 0)
            lgpio.tx_pwm(self.h, self.cfg.lpwm, DEFAULT_PWM_FREQ, duty)
        else:
            lgpio.tx_pwm(self.h, self.cfg.rpwm, DEFAULT_PWM_FREQ, 0)
            lgpio.tx_pwm(self.h, self.cfg.lpwm, DEFAULT_PWM_FREQ, 0)

    def stop(self):
        self.set_speed(0)

    def cleanup(self):
        if self.mock or not LGPIO_AVAILABLE or self.h is None:
            return
        try:
            lgpio.tx_pwm(self.h, self.cfg.rpwm, DEFAULT_PWM_FREQ, 0)
            lgpio.tx_pwm(self.h, self.cfg.lpwm, DEFAULT_PWM_FREQ, 0)
            lgpio.gpio_write(self.h, self.cfg.r_en, 0)
            lgpio.gpio_write(self.h, self.cfg.l_en, 0)
            for pin in (self.cfg.rpwm, self.cfg.lpwm, self.cfg.r_en, self.cfg.l_en):
                lgpio.gpio_free(self.h, pin)
        except Exception as e:
            print(f"  (cleanup warning for {self.cfg.name}: {e})")


class UltrasonicSensor:
    """Controls one HC-SR04 ultrasonic distance sensor."""

    def __init__(self, handle: Optional[int], cfg: UltrasonicConfig, mock: bool = False):
        self.h = handle
        self.cfg = cfg
        self.mock = mock

    def setup(self):
        if self.mock or not LGPIO_AVAILABLE or self.h is None:
            return
        lgpio.gpio_claim_output(self.h, self.cfg.trig, 0)
        lgpio.gpio_claim_input(self.h, self.cfg.echo)

    def measure_cm(self, temperature_c: float = DEFAULT_TEMPERATURE_C,
                   timeout: float = DEFAULT_ECHO_TIMEOUT_S) -> Optional[float]:
        """
        Trigger a single ping and return distance in cm, or None if the
        sensor timed out.
        """
        if self.mock or not LGPIO_AVAILABLE or self.h is None:
            # In mock mode, simulate a clear path
            return 150.0

        # 10 microsecond trigger pulse
        lgpio.gpio_write(self.h, self.cfg.trig, 1)
        time.sleep(0.00001)
        lgpio.gpio_write(self.h, self.cfg.trig, 0)

        # Wait for echo pin to go HIGH (start of return pulse)
        t0 = time.perf_counter()
        while lgpio.gpio_read(self.h, self.cfg.echo) == 0:
            if time.perf_counter() - t0 > timeout:
                return None
        pulse_start = time.perf_counter()

        # Wait for echo pin to go LOW again (end of return pulse)
        while lgpio.gpio_read(self.h, self.cfg.echo) == 1:
            if time.perf_counter() - pulse_start > timeout:
                return None
        pulse_end = time.perf_counter()

        duration_s = pulse_end - pulse_start
        speed_of_sound_m_s = 331.3 + 0.606 * temperature_c
        distance_cm = (duration_s * speed_of_sound_m_s * 100.0) / 2.0

        if distance_cm <= 0 or distance_cm > self.cfg.max_distance_cm:
            return None
        return round(distance_cm, 1)

    def cleanup(self):
        if self.mock or not LGPIO_AVAILABLE or self.h is None:
            return
        try:
            lgpio.gpio_free(self.h, self.cfg.trig)
            lgpio.gpio_free(self.h, self.cfg.echo)
        except Exception as e:
            print(f"  (cleanup warning for {self.cfg.name}: {e})")


class RobotController:
    """
    Coordinates GPIO handle and configured BTS7960 motors + HC-SR04 sensors.
    Supports differential drive kinematics and multi-motor layouts.
    """

    def __init__(self,
                 motor_configs: List[MotorConfig],
                 sensor_configs: List[UltrasonicConfig],
                 gpio_chip: int = DEFAULT_GPIO_CHIP,
                 mock: bool = False):
        self.gpio_chip = gpio_chip
        self.mock = mock or (not LGPIO_AVAILABLE)
        self.h: Optional[int] = None
        self.motor_configs = motor_configs
        self.sensor_configs = sensor_configs
        self.motors: List[MotorDriver] = []
        self.sensors: List[UltrasonicSensor] = []

    def setup(self):
        if not self.mock and LGPIO_AVAILABLE:
            try:
                self.h = lgpio.gpiochip_open(self.gpio_chip)
            except Exception as e:
                print(f"[RobotController] Warning: Failed to open gpiochip{self.gpio_chip}: {e}. Falling back to mock mode.")
                self.mock = True
                self.h = None
        else:
            self.mock = True

        for cfg in self.motor_configs:
            m = MotorDriver(self.h, cfg, mock=self.mock)
            m.setup()
            self.motors.append(m)

        for cfg in self.sensor_configs:
            s = UltrasonicSensor(self.h, cfg, mock=self.mock)
            s.setup()
            self.sensors.append(s)

    def set_motor_speeds(self, left_speed: int, right_speed: int):
        """
        Set speed for left and right drive sides.
        - If 1 motor: uses left_speed (or average).
        - If 2 motors: motor[0] is Left, motor[1] is Right.
        - If 4 motors: motors[0, 2] are Left, motors[1, 3] are Right.
        """
        n = len(self.motors)
        if n == 0:
            return
        if n == 1:
            self.motors[0].set_speed(left_speed)
        elif n == 2:
            self.motors[0].set_speed(left_speed)
            self.motors[1].set_speed(right_speed)
        elif n == 4:
            # 4WD / skid-steer
            self.motors[0].set_speed(left_speed)
            self.motors[1].set_speed(right_speed)
            self.motors[2].set_speed(left_speed)
            self.motors[3].set_speed(right_speed)
        else:
            # Generic split across motors
            mid = n // 2
            for m in self.motors[:mid]:
                m.set_speed(left_speed)
            for m in self.motors[mid:]:
                m.set_speed(right_speed)

    def set_differential_drive(self,
                               linear_x: float,
                               angular_z: float,
                               track_width: float = 0.62,
                               max_linear_speed: float = 1.0,
                               max_angular_speed: float = 2.0):
        """
        Converts linear (m/s) and angular (rad/s) velocities to motor duty cycles (-100 to 100).
        """
        if abs(linear_x) < 1e-4 and abs(angular_z) < 1e-4:
            self.stop_all_motors()
            return

        v_left = linear_x - (angular_z * track_width / 2.0)
        v_right = linear_x + (angular_z * track_width / 2.0)

        duty_left = (v_left / max_linear_speed) * 100.0
        duty_right = (v_right / max_linear_speed) * 100.0

        max_val = max(abs(duty_left), abs(duty_right))
        if max_val > 100.0:
            scale = 100.0 / max_val
            duty_left *= scale
            duty_right *= scale

        self.set_motor_speeds(int(round(duty_left)), int(round(duty_right)))

    def set_all_motors(self, speed: int):
        for m in self.motors:
            m.set_speed(speed)

    def stop_all_motors(self):
        for m in self.motors:
            m.stop()

    def read_all_distances(self,
                           settle_s: float = DEFAULT_SENSOR_SETTLE_S) -> Dict[str, Optional[float]]:
        """
        Reads all sensors sequentially, pausing between pings to prevent echo interference.
        """
        readings: Dict[str, Optional[float]] = {}
        for s in self.sensors:
            readings[s.cfg.name] = s.measure_cm()
            if not self.mock and len(self.sensors) > 1:
                time.sleep(settle_s)
        return readings

    def get_closest_obstacle(self) -> Optional[float]:
        """Returns distance (cm) to the closest detected obstacle, or None."""
        readings = self.read_all_distances()
        valid = [d for d in readings.values() if d is not None]
        return min(valid) if valid else None

    def cleanup(self):
        self.stop_all_motors()
        for m in self.motors:
            m.cleanup()
        for s in self.sensors:
            s.cleanup()
        if self.h is not None and not self.mock and LGPIO_AVAILABLE:
            try:
                lgpio.gpiochip_close(self.h)
            except Exception as e:
                print(f"  (chip close warning: {e})")
            self.h = None
