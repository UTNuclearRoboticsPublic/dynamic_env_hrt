#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rcl_interfaces.msg import ParameterDescriptor, ParameterType

from sensor_msgs.msg import Joy
from std_msgs.msg import Bool
from typing import List, Dict, Set, Tuple, Any

class JoyButtonMapperNode(Node):
    """
    A ROS 2 node that subscribes to a Joy topic and publishes Boolean messages
    to multiple topics based on the state of specified buttons.

    For each monitored button:
    - When PRESSED (Joy value 1): Publishes True to its 'true_topics' and
                                 False to its 'false_topics'.
    - When RELEASED (Joy value 0): Publishes False to its 'true_topics' and
                                  True to its 'false_topics'.

    Parameters:
        input_topic (str): Topic for incoming sensor_msgs/msg/Joy.
        button_indices (List[int]): Indices of buttons to monitor.
        true_topics_str_list (List[str]): List parallel to button_indices.
            Each element is a comma-separated string of topic names to publish
            True on when the corresponding button is pressed (and False when released).
            Example: ["/topic_a,/topic_b", "/topic_c"]
        false_topics_str_list (List[str]): List parallel to button_indices.
            Each element is a comma-separated string of topic names to publish
            False on when the corresponding button is pressed (and True when released).
            Example: ["/topic_d", "/topic_e,/topic_f"]
    """
    def __init__(self):
        super().__init__('joy_button_mapper_node')

        # --- Declare Parameters ---
        input_topic_descriptor = ParameterDescriptor(
            type=ParameterType.PARAMETER_STRING,
            description='Input topic for sensor_msgs/msg/Joy messages.'
        )
        button_indices_descriptor = ParameterDescriptor(
            type=ParameterType.PARAMETER_INTEGER_ARRAY,
            description='List of button indices to monitor from the Joy message.'
        )
        true_topics_descriptor = ParameterDescriptor(
            type=ParameterType.PARAMETER_STRING_ARRAY,
            description='List of comma-separated topics to publish True on when button pressed.'
        )
        false_topics_descriptor = ParameterDescriptor(
            type=ParameterType.PARAMETER_STRING_ARRAY,
            description='List of comma-separated topics to publish False on when button pressed.'
        )

        self.declare_parameter('input_topic', descriptor=input_topic_descriptor)
        self.declare_parameter('button_indices', descriptor=button_indices_descriptor)
        self.declare_parameter('true_topics_str_list', descriptor=true_topics_descriptor)
        self.declare_parameter('false_topics_str_list', descriptor=false_topics_descriptor)

        # --- Get Parameters ---
        self.input_topic_ = self.get_parameter('input_topic').value
        self.button_indices_ = self.get_parameter('button_indices').value
        self.true_topics_str_list_ = self.get_parameter('true_topics_str_list').value
        self.false_topics_str_list_ = self.get_parameter('false_topics_str_list').value

        # --- Validate Parameters ---
        if not self.input_topic_:
            self.get_logger().fatal("Parameter 'input_topic' is required.")
            raise ValueError("Parameter 'input_topic' not set.")

        len_indices = len(self.button_indices_)
        len_true = len(self.true_topics_str_list_)
        len_false = len(self.false_topics_str_list_)

        if not (len_indices == len_true == len_false):
            self.get_logger().fatal(
                f"Parameters 'button_indices' (len {len_indices}), "
                f"'true_topics_str_list' (len {len_true}), and "
                f"'false_topics_str_list' (len {len_false}) must have the same length."
            )
            raise ValueError("Parameter list length mismatch.")

        if any(idx < 0 for idx in self.button_indices_):
             self.get_logger().fatal("Negative values found in 'button_indices'.")
             raise ValueError("Invalid negative button index.")

        if len_indices == 0:
             self.get_logger().warn("'button_indices' is empty. No mapping configured.")

        # --- Parse Topics and Prepare Mapping ---
        self.publishers_: Dict[str, rclpy.publisher.Publisher] = {}
        self.mapping_: List[Dict[str, Any]] = [] # Stores parsed mapping
        all_unique_topics: Set[str] = set()

        for i, button_index in enumerate(self.button_indices_):
            true_topics_raw = self.true_topics_str_list_[i]
            false_topics_raw = self.false_topics_str_list_[i]

            # Parse comma-separated strings into lists, removing empty strings
            true_topics = [t.strip() for t in true_topics_raw.split(',') if t.strip()]
            false_topics = [t.strip() for t in false_topics_raw.split(',') if t.strip()]

            # Add topics to the set for publisher creation
            all_unique_topics.update(true_topics)
            all_unique_topics.update(false_topics)

            # Store the parsed mapping for this button index
            self.mapping_.append({
                'index': button_index,
                'true_topics': true_topics,
                'false_topics': false_topics
            })
            self.get_logger().info(
                f"Mapping button {button_index}: "
                f"Pressed -> True on {true_topics}, False on {false_topics}"
            )

        # --- Create Publishers ---
        for topic_name in all_unique_topics:
             # Basic validation for topic name
             if not topic_name or not topic_name.startswith('/'):
                 self.get_logger().warn(f"Skipping potentially invalid topic name: '{topic_name}'")
                 continue
             self.publishers_[topic_name] = self.create_publisher(Bool, topic_name, 10)
             self.get_logger().info(f"Created publisher for topic: {topic_name}")

        # --- Initialize Subscription ---
        self.subscription = self.create_subscription(
            Joy,
            self.input_topic_,
            self.joy_callback,
            10
        )
        self.get_logger().info(f"Subscribed to Joy topic: {self.input_topic_}")


    def joy_callback(self, msg: Joy):
        """
        Callback executed on receiving a Joy message.

        Iterates through the button mappings. For each button:
        - Determines if it's pressed (1) or released (0).
        - Publishes True/False to the configured 'true_topics'.
        - Publishes False/True to the configured 'false_topics'.
        """
        num_buttons_in_msg = len(msg.buttons)

        # Prepare messages once per callback
        msg_true = Bool(data=True)
        msg_false = Bool(data=False)

        for mapping_entry in self.mapping_:
            button_index = mapping_entry['index']
            true_topics = mapping_entry['true_topics']
            false_topics = mapping_entry['false_topics']

            # Check if the button index is valid for this specific message
            if button_index >= num_buttons_in_msg:
                self.get_logger().warn(
                    f"Button index {button_index} is out of bounds for received Joy message "
                    f"(size {num_buttons_in_msg}). Skipping this button's mapping."
                )
                continue

            is_pressed = bool(msg.buttons[button_index])

            # Determine which message to send to which topic list
            msg_for_true_list = msg_true # if is_pressed else msg_false
            msg_for_false_list = msg_false # if is_pressed else msg_true

            if is_pressed:
                # Publish to 'true' topics
                for topic_name in true_topics:
                    if topic_name in self.publishers_:
                        self.publishers_[topic_name].publish(msg_for_true_list)
                    else:
                        self.get_logger().warn(f"Publisher for topic '{topic_name}' not found (should not happen).")


                # Publish to 'false' topics
                for topic_name in false_topics:
                    if topic_name in self.publishers_:
                        self.publishers_[topic_name].publish(msg_for_false_list)
                    else:
                        self.get_logger().warn(f"Publisher for topic '{topic_name}' not found (should not happen).")


def main(args=None):
    rclpy.init(args=args)
    node = None # Define node initially as None
    try:
        node = JoyButtonMapperNode()
        rclpy.spin(node)
    except (ValueError, rclpy.exceptions.ParameterException, TypeError) as e:
         # Catch potential errors during init or parameter handling
         print(f"Node initialization or parameter error: {e}")
         if node: # Log using node logger if available
             node.get_logger().fatal(f"Node initialization or parameter error: {e}")
    except KeyboardInterrupt:
        print("Node interrupted by user (Ctrl+C).")
    except Exception as e:
        print(f"An unexpected error occurred during node execution: {e}")
        if node:
            node.get_logger().error(f"An unexpected error occurred: {e}")
    finally:
        if node and rclpy.ok() and node.context.ok():
             print("Destroying node...")
             node.destroy_node()
        if rclpy.ok():
             print("Shutting down rclpy...")
             rclpy.shutdown()
        print("Joy Button Mapper node finished.")


if __name__ == '__main__':
    main()