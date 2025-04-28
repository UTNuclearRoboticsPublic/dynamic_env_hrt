import os

from ament_index_python import get_package_share_directory

from launch_ros.substitutions import FindPackageShare
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_xml.launch_description_sources import XMLLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution, TextSubstitution
from launch import LaunchDescription
from launch_ros.actions import Node, LoadComposableNodes, ComposableNodeContainer
from launch_ros.descriptions import ComposableNode

def generate_launch_description():
    ld = LaunchDescription()

    ### CONFIG FILES
    config = os.path.join(
        get_package_share_directory('dynamic_env_hrt'),
        'config',
        'panther_teaming_config.yaml'
    )

    ### CONTROLLERS
    teammate_joy_node = Node(
        package='joy_linux',
        executable='joy_linux_node',
        name='joy_node_teammate',
        output='screen',
        parameters=[config],
        remappings=[('/joy','/joy_teammate')],
    )
    ld.add_action(teammate_joy_node)

    teammate_button_mapper = Node(
        package='dynamic_env_hrt',
        executable='joy_button_mapper.py',
        name='teammate_joy_button_mapper_node',
        output='screen',
        parameters=[config]
    )
    ld.add_action(teammate_button_mapper)


    supervisor_joy_node = Node(
        package='joy_linux',
        executable='joy_linux_node',
        name='joy_node_supervisor',
        output='screen',
        parameters=[config],
        remappings=[('/joy','/joy_supervisor')],
    )
    ld.add_action(supervisor_joy_node)

    supervisor_button_mapper = Node(
        package='dynamic_env_hrt',
        executable='joy_button_mapper.py',
        name='supervisor_joy_button_mapper_node',
        output='screen',
        parameters=[config]
    )
    ld.add_action(supervisor_button_mapper)


    teleop_joy_node = Node(
        package='joy_linux',
        executable='joy_linux_node',
        name='joy_node_operator',
        output='screen',
        parameters=[config],
        remappings=[('/joy','/joy_operator')],
    )
    ld.add_action(teleop_joy_node)

    teleop_node = Node(
        package='teleop_twist_joy',
        executable='teleop_node',
        name='operator_twist_joy',
        output='screen',
        parameters=[config],
        remappings=[('/joy','/joy_operator'),
                    ('/cmd_vel','/cmd_vel_operator')],
    )
    ld.add_action(teleop_node)

    operator_button_mapper = Node(
        package='dynamic_env_hrt',
        executable='joy_button_mapper.py',
        name='operator_joy_button_mapper_node',
        output='screen',
        parameters=[config]
    )
    ld.add_action(operator_button_mapper)


    researcher_joy_node = Node(
        package='joy_linux',
        executable='joy_linux_node',
        name='joy_node_researcher',
        output='screen',
        parameters=[config],
        remappings=[('/joy','/joy_researcher')],
    )
    ld.add_action(researcher_joy_node)

    researcher_teleop_node = Node(
        package='teleop_twist_joy',
        executable='teleop_node',
        name='researcher_twist_joy',
        output='screen',
        parameters=[config],
        remappings=[('/joy','/joy_researcher'),
                    ('/cmd_vel','/cmd_vel_researcher')],
    )
    ld.add_action(researcher_teleop_node)

    researcher_button_mapper = Node(
        package='dynamic_env_hrt',
        executable='joy_button_mapper.py',
        name='researcher_joy_button_mapper_node',
        output='screen',
        parameters=[config]
    )
    ld.add_action(researcher_button_mapper)


    twist_mux_node = Node(
        package='twist_mux',
        executable='twist_mux',
        output='screen',
        remappings={('/cmd_vel_out', 'panther/cmd_vel')},
        parameters=[config]
    )
    ld.add_action(twist_mux_node)

    ### SENSORS

    # 2D LiDAR node
    lidar_2d_node = Node(
        package='urg_node',
        executable='urg_node_driver',
        name='urg_node',
        output='screen',
        parameters=[config]
    )
    ld.add_action(lidar_2d_node)

    # # Vision
    # cam_node = IncludeLaunchDescription(
    #     PythonLaunchDescriptionSource([
    #         PathJoinSubstitution([
    #             FindPackageShare('depthai_ros_driver'),
    #             'launch',
    #             'rgbd_pcl.launch.py'
    #         ])
    #     ]),
    #     launch_arguments={'params_file': config }.items()
    # )
    # ld.add_action(cam_node)

    # rear_cam_node = IncludeLaunchDescription(
    #     PythonLaunchDescriptionSource([
    #         PathJoinSubstitution([
    #             FindPackageShare('depthai_ros_driver'),
    #             'launch',
    #             'rgbd_pcl.launch.py'
    #         ])
    #     ]),
    #     launch_arguments={
    #         'params_file': config,
    #         'namespace': 'rear_oak',
    #         'name': 'rear_oak',
    #         'parent_frame': 'rear-oak-d-base-frame'
    #     }.items()
    # )
    # ld.add_action(rear_cam_node)


    ### PERCEPTION NODES

    # LiDAR leg detection
    leg_det_node = Node(
        package='dr_spaam_ros',
        executable='node.py',
        name='dr_spaam_ros',
        output='screen',
        parameters=[config]
    )
    ld.add_action(leg_det_node)

    ### TEAMING NODE

    # # Teaming experiment node
    # teaming_node = Node(
    #     package='dynamic_env_hrt',
    #     executable='teaming_experiment_node.py',
    #     name='teaming_experiment_node',
    #     output='screen',
    #     parameters=[config]
    # )
    # ld.add_action(teaming_node)


    ### OUTPUT / VISUALIZATION
    # Foxglove bridge for visualization
    viz_node = IncludeLaunchDescription(
        XMLLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('dynamic_env_hrt'),
                'launch/foxglove_bridge_launch.xml'))
    )
    ld.add_action(viz_node)

    return ld