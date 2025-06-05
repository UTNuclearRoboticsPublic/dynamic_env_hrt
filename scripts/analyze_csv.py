#!/usr/bin/env python3

import argparse
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

def convert_ns_to_hms_str(timestamp_ns: int) -> str:
    """Converts a nanosecond timestamp to a HH:MM:SS string (UTC)."""
    if pd.isna(timestamp_ns) or timestamp_ns is None: # Handles NaN and None
        return ""
    timestamp_s = timestamp_ns / 1_000_000_000.0
    dt_object = datetime.fromtimestamp(timestamp_s, tz=timezone.utc)
    return dt_object.strftime('%H:%M:%S')

def robust_csv_value_to_bool(value) -> bool:
    """
    Converts a value read from a CSV cell to a boolean.
    Handles actual booleans, strings 'True'/'False' (case-insensitive),
    numbers (0.0 -> False, other -> True), None, NaN, and pd.NA (all -> False).
    Empty strings are also treated as False.
    """
    if pd.isna(value):  # Covers None, numpy.nan, pd.NA
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)): # e.g. if CSV had 0/1
        return bool(value)
    # For strings, only "true" (case-insensitive) is True. Others (incl. empty string) are False.
    return str(value).strip().lower() == 'true'


def analyze_trial_events(input_csv_path: Path, output_csv_path: Path):
    """
    Analyzes a CSV file for trial start and end events to compute trial durations.
    Trial Start: Timestamp of the last message where 'researcher-trial-start' was True
                 before it's released.
    Trial End: Timestamp of the first message where 'researcher-trial-end' was True
               after a trial has officially started.
    """
    try:
        # When reading CSV, it's good to specify how na_values are treated if expecting empties.
        # keep_default_na=True means empty strings will also be considered NA.
        # na_filter=True (default) will try to detect NA values.
        df = pd.read_csv(input_csv_path, keep_default_na=True, na_values=[''])
    except FileNotFoundError:
        print(f"Error: Input CSV file not found at '{input_csv_path}'")
        return
    except Exception as e:
        print(f"Error reading CSV file '{input_csv_path}': {e}")
        return

    required_columns = ['timestamp', 'researcher-trial-start', 'researcher-trial-end']
    for col in required_columns:
        if col not in df.columns:
            print(f"Error: Required column '{col}' not found in the input CSV.")
            print(f"Available columns: {df.columns.tolist()}")
            return

    # Use the robust conversion function
    try:
        df['researcher-trial-start'] = df['researcher-trial-start'].apply(robust_csv_value_to_bool)
        df['researcher-trial-end'] = df['researcher-trial-end'].apply(robust_csv_value_to_bool)
    except Exception as e:
        # This catch block might be less necessary with the robust function,
        # but good for unforeseen issues during apply.
        print(f"Error during boolean conversion of event columns: {e}. Please check CSV format.")
        return


    trial_summary_data = []
    current_trial_number = 1
    
    last_start_signal_timestamp_ns = None
    active_trial_start_timestamp_ns = None

    print(f"Analyzing trials from '{input_csv_path}'...")

    for index, row in df.iterrows():
        timestamp_ns = row['timestamp']
        # These are now reliably boolean False for any "empty" or "falsy" CSV input
        is_start_event_active = row['researcher-trial-start']
        is_end_event_active = row['researcher-trial-end']

        # --- Logic for 'researcher-trial-start' (Detecting button press and release) ---
        if is_start_event_active:
            if active_trial_start_timestamp_ns is not None:
                print(f"Warning (CSV row {index + 2}): New 'researcher-trial-start' signal at {timestamp_ns} "
                      f"while trial {current_trial_number} (start confirmed at {active_trial_start_timestamp_ns}) "
                      f"was active. Aborting previous trial {current_trial_number} and starting new trial detection.")
                active_trial_start_timestamp_ns = None 
            
            last_start_signal_timestamp_ns = timestamp_ns
        
        elif last_start_signal_timestamp_ns is not None and active_trial_start_timestamp_ns is None:
            active_trial_start_timestamp_ns = last_start_signal_timestamp_ns
            print(f"Info (CSV row {index + 2}): Trial {current_trial_number} officially started. "
                  f"Start button released; effective start ROS timestamp: {active_trial_start_timestamp_ns}. "
                  f"Awaiting 'researcher-trial-end' signal.")

        # --- Logic for 'researcher-trial-end' (Detecting first press after trial start) ---
        if is_end_event_active:
            if active_trial_start_timestamp_ns is not None:
                trial_end_timestamp_ns = timestamp_ns
                trial_duration_ns = trial_end_timestamp_ns - active_trial_start_timestamp_ns
                
                if trial_duration_ns < 0:
                    print(f"Error (CSV row {index + 2}): For trial {current_trial_number}, "
                          f"end time {trial_end_timestamp_ns} (first end signal) is before start time {active_trial_start_timestamp_ns} (start signal release). "
                          "This trial will be skipped.")
                else:
                    trial_duration_s = trial_duration_ns / 1_000_000_000.0
                    start_time_hms = convert_ns_to_hms_str(active_trial_start_timestamp_ns)
                    end_time_hms = convert_ns_to_hms_str(trial_end_timestamp_ns)
                    
                    trial_summary_data.append({
                        'trial_number': current_trial_number,
                        'trial_start_time_ros_ns': active_trial_start_timestamp_ns,
                        'trial_end_time_ros_ns': trial_end_timestamp_ns,
                        'trial_start_time_hms': start_time_hms,
                        'trial_end_time_hms': end_time_hms,
                        'trial_duration_s': trial_duration_s
                    })
                    print(f"Info (CSV row {index + 2}): Trial {current_trial_number} recorded. "
                          f"Start (from release): {start_time_hms} (ROS: {active_trial_start_timestamp_ns}), "
                          f"End (first press): {end_time_hms} (ROS: {trial_end_timestamp_ns}), "
                          f"Duration: {trial_duration_s:.3f}s")
                    current_trial_number += 1
                
                active_trial_start_timestamp_ns = None
                last_start_signal_timestamp_ns = None 
            
            else: 
                print(f"Warning (CSV row {index + 2}): 'researcher-trial-end' signal at {timestamp_ns} "
                      "occurred, but no trial is currently active (e.g., start button not yet released, "
                      "previous trial already ended, or this is a continuation of a held end button after trial completion). "
                      "Ignoring this specific end signal instance.")

    if active_trial_start_timestamp_ns is not None:
        print(f"Warning: End of CSV reached, but trial {current_trial_number} "
              f"(which officially started at ROS timestamp {active_trial_start_timestamp_ns} after button release) "
              "did not have a corresponding 'researcher-trial-end' event.")
    elif last_start_signal_timestamp_ns is not None:
        print(f"Warning: End of CSV reached. A 'researcher-trial-start' signal was active "
              f"(last seen at ROS timestamp {last_start_signal_timestamp_ns}) "
              f"for which a trial (number {current_trial_number}) did not fully complete (e.g., start button never released or no end signal).")

    output_df_columns = [
        'trial_number', 
        'trial_start_time_hms', 'trial_end_time_hms', 'trial_duration_s',
        'trial_start_time_ros_ns', 'trial_end_time_ros_ns'
    ]
    output_df = pd.DataFrame(trial_summary_data, columns=output_df_columns)
    
    try:
        output_csv_path.parent.mkdir(parents=True, exist_ok=True)
        output_df.to_csv(output_csv_path, index=False)
        print(f"Trial analysis successfully saved to '{output_csv_path}'")
    except Exception as e:
        print(f"Error writing output CSV to '{output_csv_path}': {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Analyzes trial start/end times from a Joy event CSV file, focusing on start button release and first end button press."
    )
    parser.add_argument(
        "input_csv",
        type=Path,
        help="Path to the input CSV file (previously generated by bag_to_event_csv.py)."
    )
    parser.add_argument(
        "output_csv",
        type=Path,
        help="Path to save the trial analysis results CSV file."
    )
    args = parser.parse_args()

    analyze_trial_events(args.input_csv, args.output_csv)

if __name__ == '__main__':
    main()