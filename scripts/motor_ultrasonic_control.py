#!/usr/bin/env python3
"""
scripts/motor_ultrasonic_control.py

Wrapper script for rapid hardware testing of BTS7960 motors and HC-SR04 ultrasonic sensors.
Can be executed directly from the GEOFENCE workspace root:
    python3 scripts/motor_ultrasonic_control.py --mode status
    python3 scripts/motor_ultrasonic_control.py --mode ramp
    python3 scripts/motor_ultrasonic_control.py --mode obstacle
"""

import os
import sys

# Ensure virtual_geofence package is on path if running before colcon build
ws_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src_pkg = os.path.join(ws_root, 'src', 'virtual_geofence')
if src_pkg not in sys.path:
    sys.path.insert(0, src_pkg)

from virtual_geofence.motor_ultrasonic_control import main

if __name__ == '__main__':
    main()
