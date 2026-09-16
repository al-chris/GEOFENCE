#!/usr/bin/env python3
"""
motor_controller_node.py

ROS 2 node for Raspberry Pi 5 motor and ultrasonic control.
Subscribes to `/cmd_vel` (Twist), converts to differential PWM drive commands for BTS7960,
polls HC-SR04 ultrasonic sensor(s), publishes sensor_msgs/msg/Range, and enforces
obstacle safety braking.
"""

from typing import Dict, Optional

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Range
from std_msgs.msg import Bool, Float32

from virtual_geofence.hardware_controller import (
    DEFAULT_GPIO_CHIP,
    DEFAULT_MOTORS,
    DEFAULT_OBSTACLE_STOP_CM,
    DEFAULT_SENSORS,
    LGPIO_AVAILABLE,
    RobotController,
)


class MotorControllerNode(Node):
    """
    ROS 2 Node interfacing /cmd_vel with BTS7960 motor drivers and HC-SR04 ultrasonic sensors.
    """

    def __init__(self):
        super().__init__('motor_controller_node')

        # Declare parameters
        self.declare_parameter('gpio_chip', DEFAULT_GPIO_CHIP)
        self.declare_parameter('pwm_freq', 1000)
        self.declare_parameter('track_width', 0.62)
        self.declare_parameter('max_linear_speed', 1.0)
        self.declare_parameter('max_angular_speed', 2.0)
        self.declare_parameter('obstacle_stop_cm', DEFAULT_OBSTACLE_STOP_CM)
        self.declare_parameter('obstacle_avoidance_enabled', True)
        self.declare_parameter('cmd_vel_timeout', 0.5)
        self.declare_parameter('mock_hardware', not LGPIO_AVAILABLE)
        self.declare_parameter('sensor_poll_rate_hz', 10.0)

        # Retrieve parameters
        self.gpio_chip = self.get_parameter('gpio_chip').value
        self.track_width = float(self.get_parameter('track_width').value)
        self.max_linear_speed = float(self.get_parameter('max_linear_speed').value)
        self.max_angular_speed = float(self.get_parameter('max_angular_speed').value)
        self.obstacle_stop_cm = float(self.get_parameter('obstacle_stop_cm').value)
        self.obstacle_avoidance_enabled = bool(self.get_parameter('obstacle_avoidance_enabled').value)
        self.cmd_vel_timeout = float(self.get_parameter('cmd_vel_timeout').value)
        self.mock_hardware = bool(self.get_parameter('mock_hardware').value)
        poll_rate = float(self.get_parameter('sensor_poll_rate_hz').value)

        # Initialize hardware controller
        self.robot = RobotController(
            motor_configs=DEFAULT_MOTORS,
            sensor_configs=DEFAULT_SENSORS,
            gpio_chip=self.gpio_chip,
            mock=self.mock_hardware,
        )
        self.robot.setup()

        # State tracking
        self._last_linear_x = 0.0
        self._last_angular_z = 0.0
        self._last_cmd_time = self.get_clock().now()
        self._closest_dist_cm: Optional[float] = None
        self._obstacle_blocked = False

        # Subscriptions & Publishers
        self.cmd_sub = self.create_subscription(
            Twist,
            '/cmd_vel',
            self.cmd_vel_callback,
            10
        )

        self.range_pubs: Dict[str, rclpy.publisher.Publisher] = {}
        for sensor in DEFAULT_SENSORS:
            topic = f'/sensors/ultrasonic/{sensor.name}/range'
            self.range_pubs[sensor.name] = self.create_publisher(Range, topic, 10)

        self.obstacle_pub = self.create_publisher(Bool, '/mower/obstacle_warning', 10)
        self.dist_pub = self.create_publisher(Float32, '/sensors/ultrasonic/closest_distance_cm', 10)

        # Timers
        sensor_period = 1.0 / max(0.5, poll_rate)
        self.sensor_timer = self.create_timer(sensor_period, self.poll_sensors)
        self.watchdog_timer = self.create_timer(0.1, self.check_watchdog)

        self.get_logger().info(
            f'MotorControllerNode started. '
            f'Mock: {self.robot.mock}, Chip: {self.gpio_chip}, '
            f'Obstacle Stop: {self.obstacle_stop_cm} cm'
        )

    def cmd_vel_callback(self, msg: Twist):
        self._last_cmd_time = self.get_clock().now()
        linear_x = msg.linear.x
        angular_z = msg.angular.z

        self._last_linear_x = linear_x
        self._last_angular_z = angular_z

        # Check obstacle safety if moving forward
        if self.obstacle_avoidance_enabled and linear_x > 0.0:
            if self._closest_dist_cm is not None and self._closest_dist_cm <= self.obstacle_stop_cm:
                if not self._obstacle_blocked:
                    self.get_logger().warn(
                        f'Obstacle detected at {self._closest_dist_cm:.1f} cm <= {self.obstacle_stop_cm:.1f} cm! '
                        f'Halting forward drive.'
                    )
                    self._obstacle_blocked = True
                self.robot.stop_all_motors()
                return

        self._obstacle_blocked = False
        self.robot.set_differential_drive(
            linear_x=linear_x,
            angular_z=angular_z,
            track_width=self.track_width,
            max_linear_speed=self.max_linear_speed,
            max_angular_speed=self.max_angular_speed,
        )

    def poll_sensors(self):
        distances = self.robot.read_all_distances()
        valid = [d for d in distances.values() if d is not None]
        self._closest_dist_cm = min(valid) if valid else None

        now = self.get_clock().now().to_msg()

        for sensor_name, dist_cm in distances.items():
            if sensor_name in self.range_pubs:
                r_msg = Range()
                r_msg.header.stamp = now
                r_msg.header.frame_id = f'{sensor_name}_ultrasonic_link'
                r_msg.radiation_type = Range.ULTRASOUND
                r_msg.field_of_view = 0.26  # ~15 degrees
                r_msg.min_range = 0.02      # 2 cm
                r_msg.max_range = 4.00      # 4 m
                r_msg.range = (dist_cm / 100.0) if dist_cm is not None else float('inf')
                self.range_pubs[sensor_name].publish(r_msg)

        if self._closest_dist_cm is not None:
            f_msg = Float32()
            f_msg.data = float(self._closest_dist_cm)
            self.dist_pub.publish(f_msg)

        # Publish obstacle flag
        is_obstacle = (
            self._closest_dist_cm is not None
            and self._closest_dist_cm <= self.obstacle_stop_cm
        )
        bool_msg = Bool()
        bool_msg.data = is_obstacle
        self.obstacle_pub.publish(bool_msg)

        # If obstacle appeared while moving forward, brake immediately
        if is_obstacle and self.obstacle_avoidance_enabled and self._last_linear_x > 0.0:
            self.robot.stop_all_motors()

    def check_watchdog(self):
        elapsed = (self.get_clock().now() - self._last_cmd_time).nanoseconds / 1e9
        if elapsed > self.cmd_vel_timeout and (abs(self._last_linear_x) > 1e-4 or abs(self._last_angular_z) > 1e-4):
            self.get_logger().debug(f'cmd_vel timeout ({elapsed:.2f}s) - stopping motors.')
            self.robot.stop_all_motors()
            self._last_linear_x = 0.0
            self._last_angular_z = 0.0

    def destroy_node(self):
        self.get_logger().info('Shutting down motor controller and releasing GPIO.')
        self.robot.cleanup()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MotorControllerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
