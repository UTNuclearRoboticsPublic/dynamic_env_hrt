#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rcl_interfaces.msg import ParameterDescriptor, ParameterType

from sensor_msgs.msg import Joy
from std_msgs.msg import Bool
from typing import List, Dict

class JoyButtonMapperNode(Node):
    """
    A ROS 2 node that subscribes to a Joy topic and publishes Boolean messages
    based on the state of specified buttons.

    Parameters:
        input_topic (str): The topic name for the incoming sensor_msgs/msg/Joy messages.
        button_indices (List[int]): A list of non-negative integers representing the
                                     indices of the buttons to monitor in the Joy message's
                                     'buttons' array.
        output_topics (List[str]): A list of topic names corresponding to each button
                                   index. A std_msgs/msg/Bool message will be published
                                   on the i-th topic based on the state of the button
                                   at the i-th index in 'button_indices'.
                                   Must be the same length as 'button_indices'.
    """
    def __init__(self):
        super().__init__('joy_button_mapper_node')

        # --- Declare Parameters ---
        # Input Topic Parameter
        input_topic_descriptor = ParameterDescriptor(
            type=ParameterType.PARAMETER_STRING,
            description='Input topic for sensor_msgs/msg/Joy messages.'
        )
        self.declare_parameter('input_topic', '', input_topic_descriptor) # Default empty, requires user input

        # Button Indices Parameter
        button_indices_descriptor = ParameterDescriptor(
            type=ParameterType.PARAMETER_INTEGER_ARRAY,
            description='List of button indices to monitor from the Joy message.'
        )
        self.declare_parameter('button_indices', [], button_indices_descriptor) # Default empty

        # Output Topics Parameter
        output_topics_descriptor = ParameterDescriptor(
            type=ParameterType.PARAMETER_STRING_ARRAY,
            description='List of output topics for std_msgs/msg/Bool messages. Must match length of button_indices.'
        )
        self.declare_parameter('output_topics', [], output_topics_descriptor) # Default empty

        # --- Get Parameters ---
        self.input_topic_ = self.get_parameter('input_topic').get_parameter_value().string_value
        self.button_indices_ = self.get_parameter('button_indices').get_parameter_value().integer_array_value
        self.output_topics_ = self.get_parameter('output_topics').get_parameter_value().string_array_value

        # --- Validate Parameters ---
        if not self.input_topic_:
            self.get_logger().fatal("Parameter 'input_topic' is required and cannot be empty.")
            raise ValueError("Parameter 'input_topic' not set.")

        if not self.button_indices_:
            self.get_logger().warn("Parameter 'button_indices' is empty. No buttons will be mapped.")
            # Allow running, but it won't do anything useful

        if len(self.button_indices_) != len(self.output_topics_):
            self.get_logger().fatal(
                f"Parameter 'button_indices' (length {len(self.button_indices_)}) "
                f"and 'output_topics' (length {len(self.output_topics_)}) "
                f"must have the same length."
            )
            raise ValueError("Mismatch between button_indices and output_topics length.")

        if any(idx < 0 for idx in self.button_indices_):
             self.get_logger().fatal("Parameter 'button_indices' contains negative values. Indices must be non-negative.")
             raise ValueError("Invalid negative button index.")

        # --- Initialize Publishers ---
        self.publishers_: Dict[str, rclpy.publisher.Publisher] = {}
        for topic_name in self.output_topics_:
            if not topic_name:
                 self.get_logger().fatal("Empty string found in 'output_topics'. All output topics must be valid names.")
                 raise ValueError("Invalid empty output topic name.")
            self.publishers_[topic_name] = self.create_publisher(Bool, topic_name, 10)
            self.get_logger().info(f"Created publisher for topic: {topic_name}")

        # --- Initialize Subscription ---
        self.subscription = self.create_subscription(
            Joy,
            self.input_topic_,
            self.joy_callback,
            10  # QoS profile depth
        )
        self.get_logger().info(f"Subscribed to Joy topic: {self.input_topic_}")
        self.get_logger().info(f"Mapping button indices {self.button_indices_} to topics {self.output_topics_}")


    def joy_callback(self, msg: Joy):
        """
        Callback function executed when a Joy message is received.

        Iterates through the specified button indices and publishes the
        corresponding boolean state to the associated output topics.
        """
        num_buttons_in_msg = len(msg.buttons)

        for i, button_index in enumerate(self.button_indices_):
            output_topic = self.output_topics_[i]
            publisher = self.publishers_[output_topic]

            # Check if the requested button index is valid for this message
            if button_index >= num_buttons_in_msg:
                self.get_logger().warn(
                    f"Button index {button_index} is out of bounds for received Joy message "
                    f"(size {num_buttons_in_msg}) on topic {self.input_topic_}. Skipping."
                )
                continue # Skip this button for this message

            # Determine the boolean state (Joy buttons are typically 0 or 1)
            # The prompt asks "If the i^th integer in the input integer array is true..."
            # This interpretation assumes the *value* at that index in the Joy message determines the output.
            # A Joy button message `buttons` field usually contains 0 (released) or 1 (pressed).
            # So, we check if the value at `msg.buttons[button_index]` is non-zero (effectively True).
            button_state = bool(msg.buttons[button_index])

            # Create and publish the Bool message
            bool_msg = Bool()
            bool_msg.data = button_state
            publisher.publish(bool_msg)
            # self.get_logger().debug(f"Published {bool_msg.data} to {output_topic} for button index {button_index}") # Optional debug logging


def main(args=None):
    rclpy.init(args=args)
    try:
        joy_button_mapper = JoyButtonMapperNode()
        rclpy.spin(joy_button_mapper)
    except (ValueError, rclpy.exceptions.ParameterNotDeclaredException, rclpy.exceptions.InvalidParameterValueException) as e:
         # Log fatal during init already covers this, but catch just in case
         print(f"Node initialization failed: {e}")
    except KeyboardInterrupt:
        pass # Expected on Ctrl+C
    except Exception as e:
        print(f"An unexpected error occurred: {e}") # Log any other exceptions
    finally:
        # Ensure cleanup happens even if errors occur during spin
        if 'joy_button_mapper' in locals() and rclpy.ok():
             joy_button_mapper.destroy_node()
        if rclpy.ok():
             rclpy.shutdown()
        print("Joy Button Mapper node shut down cleanly.")


if __name__ == '__main__':
    main()