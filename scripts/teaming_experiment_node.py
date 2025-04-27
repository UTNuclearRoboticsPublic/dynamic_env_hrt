#!/usr/bin/env python3

import rclpy
from rclpy.node import Node

from std_msgs.msg import Bool, Empty, String, UInt32MultiArray


class TeamExperimentNode(Node):
    def __init__(self):
        super().__init__('team_experiment_node')

        # Initialize marker command parameters
        self.id_parameters = {
            '1': {'role':'supervisor', 'cmd':'enable-auto'},
            '2': {'role':'supervisor', 'cmd':'enable-teleop'},
            '3': {'role':'supervisor', 'cmd':'estop'},
            '6': {'role':'controller', 'cmd':'start-trial'},
            '7': {'role':'controller', 'cmd':'end-trial'},
            '10': {'role':'teammate', 'cmd':'estop'},
            '11': {'role':'operator', 'cmd':'estop'}
        }

        # Create subscribers to the two topics


        # self.subscription_rear = self.create_subscription(
        #     Twist,
        #     '/philbart/joy_teleop/cmd_vel_master',
        #     self.empty_callback,
        #     1
        # )
        # self.subscription_rear = self.create_subscription(
        #     Twist,
        #     '/philbart/joy_teleop/cmd_vel_auto',
        #     self.empty_callback,
        #     1
        # )
        # self.subscription_rear = self.create_subscription(
        #     Twist,
        #     '/philbart/joy_teleop/cmd_vel',
        #     self.empty_callback,
        #     1
        # )
        # Initialize messages
        self.e_stop_msg = Bool()
        self.disable_nav_msg = Bool()
        self.pause_nav_msg = Bool()
        self.cancel_nav_msg = Empty()
        self.markers_visible = UInt32MultiArray()
        self.status_string = String()
        self.status_string.data = 'init'

        # Create publishers for the /stop and /pause topics
        self.e_stop_publisher = self.create_publisher(Bool, '/hrt_exp_e_stop', 10)
        self.disable_nav_publisher = self.create_publisher(Bool, '/disable_nav', 10)
        self.status_pub = self.create_publisher(String, '~/status', 10)
        self.command_pub = self.create_publisher(String, '~/commands', 10)
        self.markers_vis_pub = self.create_publisher(UInt32MultiArray, '~/markers_visible', 10)

        # Initialize with nav paused/disabled, and teleop enabled
        self.e_stop_msg.data = False
        self.pause_nav_msg.data = True
        self.disable_nav_msg.data = True
        self.route_loaded = False

        self.e_stop_publisher.publish(self.e_stop_msg)
        self.disable_nav_publisher.publish(self.disable_nav_msg)

        self.get_logger().info('Teaming experiment node started')

    def empty_callback(self,msg):
        pass

    


# Main function to initialize and spin the node
def main(args=None):
    rclpy.init(args=args)

    node = TeamExperimentNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down node.')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()