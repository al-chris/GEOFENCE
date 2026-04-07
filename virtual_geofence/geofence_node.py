import os
import yaml
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix
from geometry_msgs.msg import Twist
from shapely.geometry import Point, Polygon
from filterpy.kalman import KalmanFilter

try:
    import RPi.GPIO as GPIO
except Exception:
    GPIO = None


class GeoFenceNode(Node):
    def __init__(self):
        super().__init__('geofence_node')

        # Parameters
        self.declare_parameter('boundary_coords', [])
        self.declare_parameter('kalman_process_noise', 0.01)
        self.declare_parameter('kalman_measurement_noise', 2.5)

        raw = self.get_parameter('boundary_coords').value
        if len(raw) < 6 or len(raw) % 2 != 0:
            self.get_logger().fatal(
                'boundary_coords must have >= 3 pairs of [lat, lon]. Shutting down.'
            )
            raise SystemExit(1)

        coords = [
            (raw[i + 1], raw[i])
            for i in range(0, len(raw), 2)
        ]
        self.boundary = Polygon(coords)
        self.get_logger().info(f'Boundary loaded with {len(coords)} vertices.')

        # GPIO setup (optional on non-Pi platforms)
        self._gpio_ready = False
        self.buzzer_pin = 17
        self.red_led = 27
        self.green_led = 22
        if GPIO is not None:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.buzzer_pin, GPIO.OUT, initial=GPIO.LOW)
                GPIO.setup(self.red_led, GPIO.OUT, initial=GPIO.LOW)
                GPIO.setup(self.green_led, GPIO.OUT, initial=GPIO.HIGH)
                self._gpio_ready = True
            except Exception as e:
                self.get_logger().error(f'GPIO init failed: {e}. Running without GPIO.')
        else:
            self.get_logger().info('RPi.GPIO not available — running without GPIO.')

        # Kalman filter (state: lat, lon, lat_vel, lon_vel)
        q = self.get_parameter('kalman_process_noise').value
        r = self.get_parameter('kalman_measurement_noise').value

        self.kf = KalmanFilter(dim_x=4, dim_z=2)
        self.kf.x = np.zeros(4)
        self._kf_initialised = False

        dt = 0.1
        self.kf.F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
        self.kf.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ])
        self.kf.P = np.diag([1e-4, 1e-4, 1e-6, 1e-6])
        self.kf.Q = np.eye(4) * q
        self.kf.R = np.eye(2) * r

        # State tracking
        self._last_inside: bool | None = None

        # ROS I/O
        self.subscription = self.create_subscription(
            NavSatFix, '/gps/fix', self.gps_callback, 10
        )
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        self.get_logger().info('Virtual Geo-fencing Node started.')

    def gps_callback(self, msg: NavSatFix):
        # Some drivers may send a status field; skip invalid fixes
        status_ok = True
        if hasattr(msg, 'status') and getattr(msg.status, 'status', 0) < 0:
            status_ok = False

        if not status_ok:
            self.get_logger().warning('No GPS fix yet — skipping.')
            return

        lat_raw, lon_raw = msg.latitude, msg.longitude

        if not self._kf_initialised:
            self.kf.x = np.array([lat_raw, lon_raw, 0.0, 0.0])
            self._kf_initialised = True
            self.get_logger().info(
                f'Kalman filter initialised at ({lat_raw:.6f}, {lon_raw:.6f})'
            )

        z = np.array([lat_raw, lon_raw])
        self.kf.predict()
        self.kf.update(z)

        f_lat = float(self.kf.x[0])
        f_lon = float(self.kf.x[1])

        self.get_logger().debug(
            f'Raw: ({lat_raw:.7f}, {lon_raw:.7f})  '
            f'Filtered: ({f_lat:.7f}, {f_lon:.7f})'
        )

        point = Point(f_lon, f_lat)
        inside = self.boundary.contains(point)

        if inside != self._last_inside:
            self._last_inside = inside
            self._update_gpio(inside)
            if not inside:
                self.publish_stop()
                self.get_logger().warning(
                    f'BOUNDARY CROSSED → OUTSIDE | ({f_lat:.6f}, {f_lon:.6f})'
                )
            else:
                self.get_logger().info(
                    f'Re-entered boundary | ({f_lat:.6f}, {f_lon:.6f})'
                )

    def _update_gpio(self, inside: bool):
        if not self._gpio_ready:
            return
        try:
            GPIO.output(self.green_led, GPIO.HIGH if inside else GPIO.LOW)
            GPIO.output(self.red_led, GPIO.LOW if inside else GPIO.HIGH)
            GPIO.output(self.buzzer_pin, GPIO.LOW if inside else GPIO.HIGH)
        except Exception as e:
            self.get_logger().error(f'GPIO write error: {e}')

    def publish_stop(self):
        msg = Twist()
        self.cmd_pub.publish(msg)
        self.get_logger().info('Stop command published to /cmd_vel')

    def destroy_node(self):
        if self._gpio_ready:
            try:
                GPIO.cleanup()
            except Exception:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GeoFenceNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
