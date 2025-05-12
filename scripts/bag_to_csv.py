#!/usr/bin/env python3

import argparse
import yaml
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone # Added for UTC datetime conversion

# ROS 2 specific imports for bag reading and message deserialization
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message
# Import the Joy message type, assuming it's available in the environment
try:
    from sensor_msgs.msg import Joy
except ImportError:
    print("Error: sensor_msgs.msg.Joy not found. Make sure your ROS 2 environment is sourced.")
    exit(1)


def load_and_process_config(config_path: Path) -> dict:
    """
    Loads the YAML configuration file and processes it into a usable format.

    Returns:
        A dictionary containing:
        - 'all_event_names': A sorted list of unique event names for DataFrame columns.
        - 'topic_to_config_map': A dict mapping topic names to their user config
                                (including user_name and button_to_event_map).
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    all_event_names_set = set()
    topic_to_config_map = {}

    if 'users' not in config or not isinstance(config['users'], list):
        raise ValueError("Configuration error: 'users' list not found or invalid.")

    for user_cfg in config['users']:
        if not all(k in user_cfg for k in ['name', 'topic', 'button_events']):
            raise ValueError(f"Incomplete user configuration: {user_cfg.get('name', 'Unknown')}")

        topic = user_cfg['topic']
        button_events = user_cfg['button_events'] # {button_idx: event_name}

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

    if not all_event_names_set:
        raise ValueError("No events defined in the configuration file.")

    return {
        'all_event_names': sorted(list(all_event_names_set)),
        'topic_to_config_map': topic_to_config_map
    }


def process_bag_file(bag_file_path: Path, processed_config: dict, output_csv_path: Path):
    """
    Reads a ROS2 bag file, processes Joy messages based on the config,
    and saves the results (only rows with active events) to a CSV file.
    """
    all_event_names = processed_config['all_event_names']
    topic_to_config_map = processed_config['topic_to_config_map']
    configured_joy_topics = set(topic_to_config_map.keys())

    data_rows = []  # List to store dictionaries, each dict is a row

    storage_options = StorageOptions(uri=str(bag_file_path), storage_id='')
    converter_options = ConverterOptions(input_serialization_format='cdr', output_serialization_format='cdr')

    reader = SequentialReader()
    try:
        reader.open(storage_options, converter_options)
    except Exception as e:
        print(f"Error opening bag file {bag_file_path} with storage_id '{storage_options.storage_id}': {e}")
        print("If using a specific bag format like mcap, you might need to specify storage_id (e.g., 'mcap').")
        common_storage_ids = ['sqlite3', 'mcap']
        opened = False
        for sid in common_storage_ids:
            print(f"Retrying with storage_id='{sid}'...")
            try:
                storage_options_retry = StorageOptions(uri=str(bag_file_path), storage_id=sid)
                reader.open(storage_options_retry, converter_options)
                opened = True
                print(f"Successfully opened with storage_id='{sid}'.")
                break
            except Exception:
                continue
        if not opened:
            print(f"Could not open bag file {bag_file_path} with common storage IDs.")
            return

    topic_type_map = {topic.name: topic.type for topic in reader.get_all_topics_and_types()}

    print(f"Starting bag file processing. Outputting {len(all_event_names)} event columns.")
    total_joy_messages_processed = 0

    while reader.has_next():
        topic_name, serialized_message, timestamp_ns = reader.read_next()

        if topic_name not in configured_joy_topics:
            continue

        msg_type_name = topic_type_map.get(topic_name)
        if msg_type_name != 'sensor_msgs/msg/Joy':
            continue
        
        total_joy_messages_processed +=1

        try:
            msg_type_class = get_message(msg_type_name)
            joy_msg = deserialize_message(serialized_message, msg_type_class)
        except Exception as e:
            print(f"Error deserializing Joy message on topic {topic_name} at {timestamp_ns}: {e}")
            continue

        current_row_data = {'timestamp': timestamp_ns}
        
        # MODIFICATION 2: Add human-readable datetime column
        timestamp_s = timestamp_ns / 1_000_000_000.0
        dt_object = datetime.fromtimestamp(timestamp_s, tz=timezone.utc)
        current_row_data['datetime'] = dt_object.isoformat()

        user_specific_config = topic_to_config_map[topic_name]
        button_to_event_map = user_specific_config['button_to_event_map']

        active_event_in_this_row = False
        for btn_idx, button_is_pressed in enumerate(joy_msg.buttons):
            if button_is_pressed:
                if btn_idx in button_to_event_map:
                    event_name = button_to_event_map[btn_idx]
                    current_row_data[event_name] = True
                    active_event_in_this_row = True # Set flag

        # MODIFICATION 1: Only add the row if at least one event was True
        if active_event_in_this_row:
            data_rows.append(current_row_data)
        
        if total_joy_messages_processed % 1000 == 0 and total_joy_messages_processed > 0:
            print(f"Processed {total_joy_messages_processed} Joy messages from configured topics...")

    print(f"Finished reading bag. Looked at {total_joy_messages_processed} Joy messages on configured topics.")
    print(f"Found {len(data_rows)} messages with at least one active event.")

    # MODIFICATION 2: Adjust column order for DataFrame creation
    final_columns = ['timestamp', 'datetime'] + all_event_names
    if not data_rows:
        print("No Joy messages with active events found in the bag file based on the configuration.")
        df = pd.DataFrame(columns=final_columns)
    else:
        df = pd.DataFrame(data_rows, columns=final_columns)

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv_path, index=False)
    print(f"Successfully saved event data to: {output_csv_path}")


def main():
    script_dir = Path(__file__).resolve().parent
    default_config_path = script_dir.parent / 'config' / 'bagfile_analysis.yaml'

    parser = argparse.ArgumentParser(
        description="Parse ROS2 bag file Joy messages to a CSV of events based on a YAML configuration."
    )
    parser.add_argument(
        "bag_file",
        type=Path,
        help="Path to the ROS2 bag file directory or single bag file (e.g., .db3 or .mcap)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path,
        help=f"Path to the YAML configuration file. Default: {default_config_path}"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        required=True,
        help="Path for the output CSV file."
    )

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