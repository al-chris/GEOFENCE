# virtual_geofence

Virtual geo-fencing ROS 2 package for an autonomous lawn mower. Implements:

- GPS Kalman filtering
- Boundary (polygon) check using Shapely
- GPIO indicators (buzzer / LEDs) on Raspberry Pi
- Publishes zero `Twist` to `/cmd_vel` when outside boundary
- Desktop mock GPS publisher for testing

See `config/boundary.yaml` for an example boundary and Kalman parameters.

## Manual Keyboard Control

To drive the robot manually in simulation or on hardware, start the system and then run the keyboard teleop node in a new terminal:

```bash
source source_all.bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

**Click the teleop terminal to focus it, then use these keys to drive:**

| Key | Action | Description |
| :--- | :--- | :--- |
| **`i`** | **Forward** | Moves the robot straight ahead. |
| **`,`** | **Backward** | Moves the robot straight back. |
| **`j`** | **Rotate Left** | Spins the robot left in place. |
| **`l`** | **Rotate Right** | Spins the robot right in place. |
| **`u`** | **Curve Left** | Drives forward while turning left. |
| **`o`** | **Curve Right** | Drives forward while turning right. |
| **`m`** | **Curve Back Left** | Reverses while turning left. |
| **`.`** | **Curve Back Right**| Reverses while turning right. |
| **`k`** or **Space** | **Stop** | Instantly stops all movement. |
| **`q`** / **`z`** | **Speed +/-** | Increases or decreases both linear and angular speed. |
| **`w`** / **`x`** | **Linear +/-** | Increases or decreases linear speed only. |
| **`e`** / **`c`** | **Angular +/-** | Increases or decreases rotation speed only. |
| **Ctrl+C** | **Quit** | Exits the teleop controller. |

For detailed instructions and troubleshooting, see [setup.md § Method C: Manual Control (Teleop)](../../setup.md#method-c-manual-control-teleop).

Build & run instructions are in the project spec (`geofence_spec.md`).
