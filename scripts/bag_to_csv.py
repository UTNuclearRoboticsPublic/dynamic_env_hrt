#!/usr/bin/env python3

import argparse
import yaml
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import json ### NEW ### - For serializing list to JSON string

# ROS 2 specific imports
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
try:
    from sensor_msgs.msg import Joy
    from geometry_msgs.msg import PoseArray
except ImportError:
    print("Error: Required message types (Joy, PoseArray) not found. Make sure your ROS 2 environment is sourced.")
    exit(1)


def load_and_process_config(config_path: Path) -> dict:
    """Loads the YAML configuration file and processes it into a usable format."""
    # This function remains unchanged from the previous version
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    detections_topic = config.get('detections_topic')
    if detections_topic:
        print(f"Found detections topic in config: {detections_topic}")
    else:
        print("Warning: 'detections_topic' not found in config. No detection data will be processed.")
    all_event_names_set = set()
    topic_to_config_map = {}
    if 'users' in config and isinstance(config['users'], list):
        for user_cfg in config['users']:
            if not all(k in user_cfg for k in ['name', 'topic', 'button_events']):
                raise ValueError(f"Incomplete user configuration: {user_cfg.get('name', 'Unknown')}")
            topic = user_cfg['topic']
            button_events = user_cfg['button_events']
            try:
                processed_button_events = {int(k): v for k, v in button_events.items()}
            except ValueError:
                raise ValueError(f"Invalid button index in config for user {user_cfg['name']}. Must be integer.")
            if topic in topic_to_config_map:
                print(f"Warning: Duplicate topic '{topic}' in config. Using last entry.")
            topic_to_config_map[topic] = {
                'user_name': user_cfg['name'],
                'button_to_event_map': processed_button_events
            }
            all_event_names_set.update(processed_button_events.values())
    else:
        print("Warning: 'users' section not found in config. No Joy events will be processed.")
    return {
        'all_event_names': sorted(list(all_event_names_set)),
        'topic_to_config_map': topic_to_config_map,
        'detections_topic': detections_topic
    }


def process_bag_file(bag_file_path: Path, processed_config: dict, output_csv_path: Path):
    """Reads a ROS2 bag, processes messages, and saves data with range lists to a CSV."""
    all_event_names = processed_config['all_event_names']
    topic_to_config_map = processed_config['topic_to_config_map']
    detections_topic = processed_config['detections_topic']

    joy_topics = set(topic_to_config_map.keys())
    all_configured_topics = joy_topics.copy()
    if detections_topic:
        all_configured_topics.add(detections_topic)

    data_rows = []

    # This section for opening the bag file remains unchanged
    storage_options = StorageOptions(uri=str(bag_file_path), storage_id='')
    converter_options = ConverterOptions(input_serialization_format='cdr', output_serialization_format='cdr')
    reader = SequentialReader()
    try:
        reader.open(storage_options, converter_options)
    except Exception:
        print("Failed to open bag with auto-detection. Retrying with common storage IDs...")
        common_storage_ids = ['sqlite3', 'mcap']
        opened = False
        for sid in common_storage_ids:
            try:
                storage_options_retry = StorageOptions(uri=str(bag_file_path), storage_id=sid)
                reader.open(storage_options_retry, converter_options)
                opened = True
                print(f"Successfully opened with storage_id='{sid}'.")
                break
            except Exception:
                continue
        if not opened:
            print(f"Could not open bag file {bag_file_path}.")
            return

    topic_type_map = {topic.name: topic.type for topic in reader.get_all_topics_and_types()}

    print("Starting bag file processing...")
    total_messages_processed = 0

    while reader.has_next():
        topic_name, serialized_message, timestamp_ns = reader.read_next()

        if topic_name not in all_configured_topics:
            continue
        
        total_messages_processed += 1
        msg_type_name = topic_type_map.get(topic_name)

        # Initialize a new row for this timestamp
        current_row_data = {'timestamp': timestamp_ns}
        timestamp_s = timestamp_ns / 1_000_000_000.0
        dt_object = datetime.fromtimestamp(timestamp_s, tz=timezone.utc)
        current_row_data['datetime'] = dt_object.isoformat()
        
        # Default event columns to False
        for event_name in all_event_names:
            current_row_data[event_name] = False
        
        # ### MODIFIED ### - Default the new columns for detections.
        # Use None/NaN as a placeholder for rows that don't have this data type.
        current_row_data['n_detections'] = np.nan
        current_row_data['detection_ranges_json'] = None # Placeholder for our JSON string

        try:
            msg_type_class = get_message(msg_type_name)
            msg = deserialize_message(serialized_message, msg_type_class)
        except Exception as e:
            print(f"Error deserializing message on topic {topic_name} at {timestamp_ns}: {e}")
            continue

        if msg_type_name == 'sensor_msgs/msg/Joy' and topic_name in joy_topics:
            user_specific_config = topic_to_config_map[topic_name]
            button_to_event_map = user_specific_config['button_to_event_map']
            for btn_idx, button_is_pressed in enumerate(msg.buttons):
                if button_is_pressed and btn_idx in button_to_event_map:
                    event_name = button_to_event_map[btn_idx]
                    current_row_data[event_name] = True
        
        elif msg_type_name == 'geometry_msgs/msg/PoseArray' and topic_name == detections_topic:
            # ### MODIFIED ### - PoseArray processing logic
            num_poses = len(msg.poses)
            current_row_data['n_detections'] = num_poses
            
            if num_poses > 0:
                # Calculate all ranges and round to a reasonable precision
                ranges = [round(np.sqrt(p.position.x**2 + p.position.y**2), 4) for p in msg.poses]
                # Serialize the list of floats into a JSON string
                current_row_data['detection_ranges_json'] = json.dumps(ranges)
            else:
                # For zero detections, store an empty JSON array string
                current_row_data['detection_ranges_json'] = json.dumps([])

        data_rows.append(current_row_data)
        
        if total_messages_processed % 1000 == 0 and total_messages_processed > 0:
            print(f"Processed {total_messages_processed} messages from configured topics...")

    print(f"Finished reading bag. Processed a total of {total_messages_processed} relevant messages.")

    # ### MODIFIED ### - Update final column list
    detection_cols = ['n_detections', 'detection_ranges_json']
    final_columns = (['timestamp', 'datetime'] + all_event_names + detection_cols)
    if not data_rows:
        print("No messages found in the bag file on any configured topic.")
        df = pd.DataFrame(columns=final_columns)
    else:
        df = pd.DataFrame(data_rows, columns=final_columns)

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv_path, index=False)
    print(f"Successfully saved combined data to: {output_csv_path}")

# main() function remains unchanged
def main():
    script_dir = Path(__file__).resolve().parent
    default_config_path = script_dir.parent / 'config' / 'bagfile_analysis.yaml'
    parser = argparse.ArgumentParser(
        description="Parse ROS2 bag file Joy and PoseArray messages to a CSV based on a YAML configuration."
    )
    parser.add_argument("bag_file",type=Path,help="Path to the ROS2 bag file directory or single bag file (e.g., .db3 or .mcap).")
    parser.add_argument("--config",type=Path,default=default_config_path,help=f"Path to the YAML configuration file. Default: {default_config_path}")
    parser.add_argument("--output", "-o",type=Path,required=True,help="Path for the output CSV file.")
    args = parser.parse_args()
    try:
        print(f"Loading configuration from: {args.config}")
        processed_config = load_and_process_config(args.config)
        print(f"Processing bag file: {args.bag_file}")
        process_bag_file(args.bag_file, processed_config, args.output)
    except FileNotFoundError as e:
        print(f"Error: {e}")
    except ValueError as e:
        print(f"Configuration Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()