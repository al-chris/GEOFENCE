from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    pkg_share = get_package_share_directory('virtual_geofence')
    default_params = os.path.join(pkg_share, 'config', 'hardware_params.yaml')
    hardware_params = LaunchConfiguration('hardware_params')

    return LaunchDescription([
        DeclareLaunchArgument(
            'hardware_params',
            default_value=default_params,
            description='Path to hardware controller parameters YAML.',
        ),

        Node(
            package='virtual_geofence',
            executable='motor_controller_node',
            name='motor_controller_node',
            output='screen',
            parameters=[hardware_params]
        ),
    ])
