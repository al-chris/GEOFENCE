"""
Tests for hardware_controller.py
Verifies driver configuration, differential drive kinematics, deadband logic,
and mock sensor behavior without requiring physical GPIO hardware.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'virtual_geofence')))

from virtual_geofence.hardware_controller import (
    DEFAULT_MOTORS,
    DEFAULT_SENSORS,
    MotorConfig,
    MotorDriver,
    RobotController,
    UltrasonicConfig,
    UltrasonicSensor,
)


class TestHardwareController(unittest.TestCase):

    def test_motor_speed_clamping_and_inversion(self):
        cfg_normal = MotorConfig(name="test_norm", rpwm=12, lpwm=13, r_en=20, l_en=21, invert=False)
        driver_norm = MotorDriver(handle=None, cfg=cfg_normal, mock=True)
        driver_norm.set_speed(150)
        self.assertEqual(driver_norm._speed, 100)
        driver_norm.set_speed(-120)
        self.assertEqual(driver_norm._speed, -100)
        driver_norm.stop()
        self.assertEqual(driver_norm._speed, 0)

        cfg_inv = MotorConfig(name="test_inv", rpwm=12, lpwm=13, r_en=20, l_en=21, invert=True)
        driver_inv = MotorDriver(handle=None, cfg=cfg_inv, mock=True)
        driver_inv.set_speed(50)
        self.assertEqual(driver_inv._speed, -50)
        driver_inv.set_speed(-70)
        self.assertEqual(driver_inv._speed, 70)

    def test_ultrasonic_mock_measurement(self):
        cfg = UltrasonicConfig(name="test_sensor", trig=23, echo=24)
        sensor = UltrasonicSensor(handle=None, cfg=cfg, mock=True)
        dist = sensor.measure_cm()
        self.assertIsNotNone(dist)
        self.assertGreater(dist, 0)

    def test_robot_controller_differential_drive(self):
        robot = RobotController(DEFAULT_MOTORS, DEFAULT_SENSORS, mock=True)
        robot.setup()

        # Straight forward
        robot.set_differential_drive(linear_x=0.5, angular_z=0.0, max_linear_speed=1.0)
        self.assertEqual(robot.motors[0]._speed, 50)
        self.assertEqual(robot.motors[1]._speed, 50)

        # Turning in place (positive angular_z = turn left: left wheels back, right wheels forward)
        robot.set_differential_drive(linear_x=0.0, angular_z=1.0, track_width=0.62, max_linear_speed=1.0)
        self.assertLess(robot.motors[0]._speed, 0)
        self.assertGreater(robot.motors[1]._speed, 0)

        # Stop command
        robot.stop_all_motors()
        for m in robot.motors:
            self.assertEqual(m._speed, 0)

        # Read distances
        readings = robot.read_all_distances()
        self.assertIn("front", readings)

        robot.cleanup()


if __name__ == '__main__':
    unittest.main()
