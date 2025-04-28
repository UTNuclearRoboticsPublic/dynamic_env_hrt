#!/bin/bash

# Check if a filename argument is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <filename>"
  exit 1
fi

# Create the file using the touch command
ros2 bag record -s mcap -o ../bags/"$1" /cmd_vel_operator /joy_supervisor /panther/odometry/filtered /panther/dr_spaam_detections /supervisor_manual /joy_teammate /supervisor_estop /researcher_auto /operator_manual /trial_start /trial_end /operator_estop /researcher_estop /joy_researcher /researcher_manual /dr_spaam_rviz /joy_operator /supervisor_auto /teammate_estop /cmd_vel_researcher