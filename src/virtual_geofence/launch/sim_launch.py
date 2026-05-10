import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.substitutions import Command, EnvironmentVariable, FindExecutable, LaunchConfiguration, PathJoinSubstitution, TextSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_name = 'virtual_geofence'
    
    # Use the existing boundary.yaml as default params if needed, 
    # though simulation might need its own or a combined one.
    # For now, we'll point to the one in the package share.
    params_file = LaunchConfiguration('params_file')
    default_params = PathJoinSubstitution([
        FindPackageShare(pkg_name),
        'config',
        'boundary.yaml',
    ])
    
    world_file = PathJoinSubstitution([
        FindPackageShare(pkg_name),
        'worlds',
        'field.sdf',
    ])
    
    model_resource_path = PathJoinSubstitution([
        FindPackageShare(pkg_name),
        'models',
    ])
    
    robot_description = ParameterValue(
        Command([
            FindExecutable(name='xacro'),
            ' ',
            PathJoinSubstitution([
                FindPackageShare(pkg_name),
                'urdf',
                'lawnmower.urdf.xacro',
            ]),
        ]),
        value_type=str
    )

    # Gazebo Sim
    gz_sim = ExecuteProcess(
        cmd=['gz', 'sim', '-r', world_file],
        output='screen',
    )

    # Spawn robot
    spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        parameters=[{
            'name': 'lawnmower',
            'topic': '/robot_description',
            'world': 'agri_robotics_field',
            'x': -7.0,
            'y': -7.0,
            'z': 0.005,
            'Y': 0.785,
        }],
        output='screen',
    )

    # Bridge
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/cmd_vel@geometry_msgs/msg/Twist@gz.msgs.Twist',
            '/odom@nav_msgs/msg/Odometry@gz.msgs.Odometry',
            '/tf@tf2_msgs/msg/TFMessage@gz.msgs.Pose_V',
            '/joint_states@sensor_msgs/msg/JointState@gz.msgs.Model',
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/imu/data_raw@sensor_msgs/msg/Imu[gz.msgs.IMU',
            '/gps/fix@sensor_msgs/msg/NavSatFix[gz.msgs.NavSat',
            '/lidar/points@sensor_msgs/msg/PointCloud2[gz.msgs.PointCloudPacked',
            '/camera/depth@sensor_msgs/msg/Image[gz.msgs.Image',
            '/camera/depth/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo',
            '/camera/nadir@sensor_msgs/msg/Image[gz.msgs.Image',
            '/camera/nadir/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo',
            '/deck/blade/cmd_vel@std_msgs/msg/Float64]gz.msgs.Double',
            '/deck/turret/cmd_pos@std_msgs/msg/Float64]gz.msgs.Double',
            '/deck/pitch/cmd_pos@std_msgs/msg/Float64]gz.msgs.Double',
        ],
        output='screen',
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Path to the geofence parameter file.',
        ),
        
        SetEnvironmentVariable(
            name='GZ_SIM_RESOURCE_PATH',
            value=[
                model_resource_path,
                TextSubstitution(text=os.pathsep),
                EnvironmentVariable('GZ_SIM_RESOURCE_PATH', default_value=''),
            ],
        ),
        SetEnvironmentVariable(
            name='GAZEBO_RESOURCE_PATH',
            value=[
                model_resource_path,
                TextSubstitution(text=os.pathsep),
                EnvironmentVariable('GAZEBO_RESOURCE_PATH', default_value=''),
            ],
        ),
        
        gz_sim,
        spawn_robot,
        bridge,
        
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_description, 'use_sim_time': True}],
        ),
        
        # The geofence node itself, consuming simulation GPS
        Node(
            package=pkg_name,
            executable='geofence_node',
            name='geofence_node',
            output='screen',
            parameters=[params_file, {'use_sim_time': True}]
        ),
    ])
