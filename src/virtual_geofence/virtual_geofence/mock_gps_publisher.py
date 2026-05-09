import math
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus


class MockGPSPublisher(Node):
    """Publishes a simulated GPS path for bench-testing."""

    def __init__(self):
        super().__init__('mock_gps')
        self.pub = self.create_publisher(NavSatFix, '/gps/fix', 10)
        self.timer = self.create_timer(0.5, self.publish_fix)
        self._t = 0.0

    def publish_fix(self):
        msg = NavSatFix()
        try:
            msg.status.status = NavSatStatus.STATUS_FIX
        except Exception:
            # Some environments may not expose STATUS_FIX constant; fall back
            msg.status.status = 0
        # Spiral path — starts inside boundary, drifts outward
        msg.latitude = 7.5185 + 0.0012 * math.sin(self._t)
        msg.longitude = 4.5165 + 0.0012 * math.cos(self._t)
        self.pub.publish(msg)
        self._t += 0.08


def main(args=None):
    rclpy.init(args=args)
    node = MockGPSPublisher()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
