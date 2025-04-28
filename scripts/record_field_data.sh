#!/bin/bash

# Check if a filename argument is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <filename>"
  exit 1
fi

# Create the file using the touch command
ros2 bag record -s mcap -o ../bags/hrt_experiments/"$1" /panther/dr_spaam_detections /teaming_experiment_node/status /teaming_experiment_node/markers_visible /teaming_experiment_node/commands