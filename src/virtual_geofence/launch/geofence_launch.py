from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    pkg_share = get_package_share_directory('virtual_geofence')
    config = os.path.join(pkg_share, 'config', 'boundary.yaml')
    params_file = LaunchConfiguration('params_file')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=config,
            description='Path to geofence ROS params YAML (boundary + filter params).',
        ),

        Node(
            package='nmea_navsat_driver',
            executable='nmea_serial_driver',
            name='gps_driver',
            output='screen',
            remappings=[
                ('fix', '/gps/fix'),
            ],
            parameters=[{
                # Use the system serial port matching your device
                'port': '/dev/ttyAMA0',
                'baud': 9600,
                'frame_id': 'gps',
            }]
        ),

        Node(
            package='virtual_geofence',
            executable='geofence_node',
            name='geofence_node',
            output='screen',
            parameters=[params_file]
        ),
    ])
