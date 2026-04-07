# virtual_geofence

Virtual geo-fencing ROS 2 package for an autonomous lawn mower. Implements:

- GPS Kalman filtering
- Boundary (polygon) check using Shapely
- GPIO indicators (buzzer / LEDs) on Raspberry Pi
- Publishes zero `Twist` to `/cmd_vel` when outside boundary
- Desktop mock GPS publisher for testing

See `config/boundary.yaml` for an example boundary and Kalman parameters.

Build & run instructions are in the project spec (`geofence_spec.md`).
