#!/usr/bin/env python3

import argparse
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
import json
import numpy as np
from collections import defaultdict

# --- Configuration (remains the same) ---
EVENT_GROUPING_THRESHOLD_NS = 75_000_000  # 75 milliseconds
EVENT_CONFIG = {
    "supervisor-stop":           {"mode": "stop",     "precedence": 1, "type": "stop_command"},
    "teammate-stop":             {"mode": "stop",     "precedence": 1, "type": "stop_command"},
    "operator-stop":             {"mode": "stop",     "precedence": 1, "type": "stop_command"},
    "researcher-enable-operator": {"mode": "operator", "precedence": 2, "type": "mode_change"},
    "supervisor-enable-operator": {"mode": "operator", "precedence": 2, "type": "mode_change"},
    "operator-enable-operator":  {"mode": "operator", "precedence": 2, "type": "mode_change"},
    "researcher-enable-autonomy": {"mode": "autonomy", "precedence": 3, "type": "mode_change"},
    "supervisor-enable-autonomy": {"mode": "autonomy", "precedence": 3, "type": "mode_change"},
    "researcher-mark-event":     {"mode": None,       "precedence": 99, "type": "segment_mark"}
}

def robust_csv_value_to_bool(value) -> bool:
    """Converts a value read from a CSV cell to a boolean robustly."""
    if pd.isna(value): return False
    if isinstance(value, bool): return value
    if isinstance(value, (int, float)): return bool(value)
    return str(value).strip().lower() == 'true'

# ### NEW ### - Pre-computation function to determine the mode for every row
def add_global_mode_timeline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Pre-processes the entire DataFrame to create a definitive mode timeline.
    Returns the DataFrame with a new 'system_mode' column.
    """
    print("Pre-computing global mode timeline...")
    event_cols = [col for col, conf in EVENT_CONFIG.items() if conf['type'] != 'segment_mark']
    
    # 1. Find all raw button press groups for mode-changing events
    event_groups = defaultdict(list)
    for event_name in event_cols:
        group = []
        for index, row in df[df[event_name]].iterrows():
            ts = row['timestamp']
            if group and (ts - group[-1]) > EVENT_GROUPING_THRESHOLD_NS:
                event_groups[event_name].append(group)
                group = [ts]
            else:
                group.append(ts)
        if group:
            event_groups[event_name].append(group)

    # 2. Finalize events with their average timestamp
    finalized_events = []
    for event_name, groups in event_groups.items():
        for group in groups:
            avg_ts = (group[0] + group[-1]) // 2
            finalized_events.append({'timestamp': avg_ts, 'event': event_name})

    if not finalized_events:
        print("No mode-changing events found in file. Assuming 'stop' mode throughout.")
        df['system_mode'] = 'stop'
        return df

    # 3. Create a DataFrame of events and resolve precedence for simultaneous events
    events_df = pd.DataFrame(finalized_events).sort_values('timestamp').reset_index(drop=True)
    events_df['precedence'] = events_df['event'].apply(lambda x: EVENT_CONFIG[x]['precedence'])
    # Keep only the highest precedence event at each timestamp
    final_transitions_df = events_df.loc[events_df.groupby('timestamp')['precedence'].idxmin()]
    
    # 4. Create the mode history timeline
    # ASSUMPTION: The system starts in 'stop' mode before the first event.
    mode_history = [(0, 'stop')] 
    for index, row in final_transitions_df.iterrows():
        new_mode = EVENT_CONFIG[row['event']]['mode']
        if new_mode != mode_history[-1][1]:
            mode_history.append((row['timestamp'], new_mode))

    # 5. Apply the mode history to the main DataFrame
    df['system_mode'] = pd.NA
    for i in range(len(mode_history)):
        start_ts = mode_history[i][0]
        mode = mode_history[i][1]
        end_ts = mode_history[i+1][0] if i + 1 < len(mode_history) else df['timestamp'].iloc[-1]
        df.loc[(df['timestamp'] >= start_ts) & (df['timestamp'] <= end_ts), 'system_mode'] = mode
    
    # Forward-fill any gaps
    df['system_mode'] = df['system_mode'].ffill().fillna('stop')
    print("Global mode timeline computed.")
    return df

def analyze_trial_slice(trial_df: pd.DataFrame, trial_start_ts: int, trial_end_ts: int):
    """
    Analyzes a slice of the DataFrame for a single trial to get all stats.
    """
    results = {}
    
    # --- 1. Get Segment Marks ---
    mark_events = []
    group = []
    for index, row in trial_df[trial_df['researcher-mark-event']].iterrows():
        ts = row['timestamp']
        if group and (ts - group[-1]) > EVENT_GROUPING_THRESHOLD_NS:
            mark_events.append((group[0] + group[-1]) // 2)
            group = [ts]
        else:
            group.append(ts)
    if group:
        mark_events.append((group[0] + group[-1]) // 2)
    
    n_marked_events = len(mark_events)
    me1_ts = mark_events[0] if n_marked_events >= 1 else np.nan
    me2_ts = mark_events[1] if n_marked_events >= 2 else np.nan
    
    # --- 2. Calculate Stats for Periods (Trial, Segments) ---
    def calculate_period_stats(period_df, period_start_ts, period_end_ts):
        stats = defaultdict(float)
        period_duration = period_end_ts - period_start_ts
        if period_duration <= 0: return {}

        # Mode Durations
        mode_durations = defaultdict(int)
        for mode, group in period_df.groupby('system_mode'):
            # This is a simplified way; for full accuracy, one must check boundaries
            # A more robust way: iterate and check time diffs
            last_ts = period_start_ts
            for idx, row in period_df.iterrows():
                mode_durations[row['system_mode']] += row['timestamp'] - last_ts
                last_ts = row['timestamp']
            mode_durations[period_df['system_mode'].iloc[-1]] += period_end_ts - last_ts

        for mode in ['stop', 'operator', 'autonomy']:
            stats[f'time_in_{mode}_s'] = mode_durations.get(mode, 0) / 1e9
            stats[f'pct_time_in_{mode}'] = (mode_durations.get(mode, 0) / period_duration) * 100 if period_duration > 0 else 0
        
        # Stop Command Counts
        for stop_cmd_type in ["supervisor-stop", "teammate-stop", "operator-stop"]:
            stats[f'n_{stop_cmd_type}'] = period_df[stop_cmd_type].sum()
            
        return stats

    # Calculate for whole trial
    results['trial'] = calculate_period_stats(trial_df, trial_start_ts, trial_end_ts)
    
    # Calculate for segments
    if n_marked_events == 2:
        results['comment'] = "OK"
        seg1_df = trial_df[trial_df['timestamp'] < me1_ts]
        results['seg1'] = calculate_period_stats(seg1_df, trial_start_ts, me1_ts)
        
        seg2_df = trial_df[(trial_df['timestamp'] >= me1_ts) & (trial_df['timestamp'] < me2_ts)]
        results['seg2'] = calculate_period_stats(seg2_df, me1_ts, me2_ts)
        
        seg3_df = trial_df[trial_df['timestamp'] >= me2_ts]
        results['seg3'] = calculate_period_stats(seg3_df, me2_ts, trial_end_ts)
    else:
        # Generate the detailed TODO comment
        relative_event_times_s = [(ts - trial_start_ts) / 1e9 for ts in mark_events]
        relative_times_str = ", ".join([f"{t:.3f}s" for t in relative_event_times_s])
        results['comment'] = f"TODO: Found {n_marked_events} events at relative times: [{relative_times_str}]"
    
    return results

def analyze_main(input_csv_path: Path, output_csv_path: Path):
    """Main function to drive the trial analysis."""
    try:
        df = pd.read_csv(input_csv_path, keep_default_na=True, na_values=[''])
    except FileNotFoundError:
        print(f"Error: Input CSV file not found at '{input_csv_path}'")
        return
        
    required_columns = ['timestamp'] + list(EVENT_CONFIG.keys())
    for col in required_columns:
        if col not in df.columns:
            print(f"Error: Required column '{col}' not found. Please check your config and CSV.")
            return
    for col in EVENT_CONFIG:
        df[col] = df[col].apply(robust_csv_value_to_bool)
        
    # --- Phase 1: Pre-compute global state ---
    df = add_global_mode_timeline(df)

    # --- Phase 2: Find trials and analyze them ---
    trial_summary_data = []
    current_trial_number = 1
    active_trial_start_index = None
    last_start_signal_ts = None
    
    print("Identifying trials and calculating in-trial statistics...")

    for index, row in df.iterrows():
        is_start_active = row['researcher-trial-start']
        is_end_active = row['researcher-trial-end']
        
        if is_start_active:
            if active_trial_start_index is not None: print(f"Warning: New 'start' event while trial {current_trial_number} was active. Aborting.")
            active_trial_start_index = None
            last_start_signal_ts = row['timestamp']
        
        elif last_start_signal_ts is not None and active_trial_start_index is None:
            active_trial_start_index = index # The row *after* the last start signal

        if is_end_active and active_trial_start_index is not None:
            # --- A complete trial has been found ---
            trial_start_ts = last_start_signal_ts
            trial_end_ts = row['timestamp']
            
            if trial_end_ts < trial_start_ts:
                print(f"Error: Trial {current_trial_number} end time before start time. Skipping.")
            else:
                # Analyze the slice of the DataFrame for this trial
                trial_df_slice = df.iloc[active_trial_start_index:index + 1]
                all_stats = analyze_trial_slice(trial_df_slice, trial_start_ts, trial_end_ts)
                
                # --- Assemble the final output row ---
                output_row = {'trial_number': current_trial_number, 'comment': all_stats.get('comment', 'ERROR')}
                # Add stats with prefixes
                for period in ['trial', 'seg1', 'seg2', 'seg3']:
                    for stat_name, value in all_stats.get(period, {}).items():
                        output_row[f"{period}_{stat_name}"] = value
                
                trial_summary_data.append(output_row)
                print(f"Info: Trial {current_trial_number} recorded. Comment: {output_row['comment']}")
                current_trial_number += 1

            active_trial_start_index, last_start_signal_ts = None, None

    if not trial_summary_data:
        print("No complete trials found to analyze.")
        return
        
    output_df = pd.DataFrame(trial_summary_data)
    
    try:
        output_csv_path.parent.mkdir(parents=True, exist_ok=True)
        output_df.to_csv(output_csv_path, index=False)
        print(f"\nFull trial analysis successfully saved to '{output_csv_path}'")
    except Exception as e:
        print(f"\nError writing output CSV: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Analyzes trial segments and mode usage from a processed event CSV.")
    parser.add_argument("input_csv", type=Path, help="Path to the input CSV file.")
    parser.add_argument("output_csv", type=Path, help="Path to save the trial analysis results.")
    args = parser.parse_args()
    analyze_main(args.input_csv, args.output_csv)
    
# import argparse
# import pandas as pd
# from datetime import datetime, timezone
# from pathlib import Path
# import json  ### NEW ###
# import numpy as np ### NEW ###

# def convert_ns_to_hms_str(timestamp_ns: int) -> str:
#     """Converts a nanosecond timestamp to a HH:MM:SS string (UTC)."""
#     if pd.isna(timestamp_ns) or timestamp_ns is None:
#         return ""
#     timestamp_s = timestamp_ns / 1_000_000_000.0
#     dt_object = datetime.fromtimestamp(timestamp_s, tz=timezone.utc)
#     return dt_object.strftime('%H:%M:%S')

# def robust_csv_value_to_bool(value) -> bool:
#     """Converts a value read from a CSV cell to a boolean robustly."""
#     if pd.isna(value):
#         return False
#     if isinstance(value, bool):
#         return value
#     if isinstance(value, (int, float)):
#         return bool(value)
#     return str(value).strip().lower() == 'true'

# def analyze_trial_events(input_csv_path: Path, output_csv_path: Path):
#     """
#     Analyzes a CSV file for trial events and summarizes detection data within each trial.
#     """
#     try:
#         df = pd.read_csv(input_csv_path, keep_default_na=True, na_values=[''])
#     except FileNotFoundError:
#         print(f"Error: Input CSV file not found at '{input_csv_path}'")
#         return
#     except Exception as e:
#         print(f"Error reading CSV file '{input_csv_path}': {e}")
#         return

#     required_columns = ['timestamp', 'researcher-trial-start', 'researcher-trial-end', 'n_detections', 'detection_ranges_json']
#     for col in required_columns:
#         if col not in df.columns:
#             print(f"Error: Required column '{col}' not found in the input CSV.")
#             print(f"Available columns: {df.columns.tolist()}")
#             return

#     df['researcher-trial-start'] = df['researcher-trial-start'].apply(robust_csv_value_to_bool)
#     df['researcher-trial-end'] = df['researcher-trial-end'].apply(robust_csv_value_to_bool)

#     trial_summary_data = []
#     current_trial_number = 1
    
#     last_start_signal_timestamp_ns = None
#     active_trial_start_timestamp_ns = None

#     ### NEW ### - Accumulators for data within a single trial
#     trial_all_ranges = []
#     trial_n_detections_list = []

#     print(f"Analyzing trials and detection data from '{input_csv_path}'...")

#     for index, row in df.iterrows():
#         timestamp_ns = row['timestamp']
#         is_start_event_active = row['researcher-trial-start']
#         is_end_event_active = row['researcher-trial-end']

#         # --- Logic for 'researcher-trial-start' ---
#         if is_start_event_active:
#             if active_trial_start_timestamp_ns is not None:
#                 print(f"Warning (CSV row {index + 2}): New 'researcher-trial-start' event while trial {current_trial_number} was active. Aborting previous trial.")
#                 active_trial_start_timestamp_ns = None 
#                 # Reset accumulators for the aborted trial
#                 trial_all_ranges = []
#                 trial_n_detections_list = []
            
#             last_start_signal_timestamp_ns = timestamp_ns
        
#         elif last_start_signal_timestamp_ns is not None and active_trial_start_timestamp_ns is None:
#             active_trial_start_timestamp_ns = last_start_signal_timestamp_ns
#             print(f"Info (CSV row {index + 2}): Trial {current_trial_number} officially started. Awaiting 'researcher-trial-end'.")
#             # Initialize accumulators for the new trial
#             trial_all_ranges = []
#             trial_n_detections_list = []

#         ### NEW ### --- Accumulate detection data if a trial is active ---
#         # This block runs for every row, checking if it's within an active trial period.
#         if active_trial_start_timestamp_ns is not None:
#             # Check if the current row contains detection data.
#             # pd.notna checks for both None and NaN.
#             if pd.notna(row['detection_ranges_json']):
#                 try:
#                     # Append the number of detections from this message to our list for this trial
#                     trial_n_detections_list.append(row['n_detections'])
#                     # Parse the JSON string and extend the list of all ranges for this trial
#                     ranges_from_row = json.loads(row['detection_ranges_json'])
#                     if ranges_from_row: # Only extend if the list is not empty
#                         trial_all_ranges.extend(ranges_from_row)
#                 except (json.JSONDecodeError, TypeError) as e:
#                     print(f"Warning (CSV row {index + 2}): Could not parse 'detection_ranges_json'. Value: '{row['detection_ranges_json']}'. Error: {e}")

#         # --- Logic for 'researcher-trial-end' ---
#         if is_end_event_active:
#             if active_trial_start_timestamp_ns is not None:
#                 trial_end_timestamp_ns = timestamp_ns
#                 trial_duration_ns = trial_end_timestamp_ns - active_trial_start_timestamp_ns
                
#                 if trial_duration_ns < 0:
#                     print(f"Error (CSV row {index + 2}): For trial {current_trial_number}, end time is before start time. Skipping.")
#                 else:
#                     trial_duration_s = trial_duration_ns / 1_000_000_000.0
#                     start_time_hms = convert_ns_to_hms_str(active_trial_start_timestamp_ns)
#                     end_time_hms = convert_ns_to_hms_str(trial_end_timestamp_ns)
                    
#                     ### NEW ### - Compute summary statistics for the completed trial
#                     trial_stats = {
#                         'min_range_in_trial': np.min(trial_all_ranges) if trial_all_ranges else np.nan,
#                         'max_range_in_trial': np.max(trial_all_ranges) if trial_all_ranges else np.nan,
#                         'mean_range_in_trial': np.mean(trial_all_ranges) if trial_all_ranges else np.nan,
#                         'min_n_detections_per_msg': np.min(trial_n_detections_list) if trial_n_detections_list else np.nan,
#                         'max_n_detections_per_msg': np.max(trial_n_detections_list) if trial_n_detections_list else np.nan,
#                         'mean_n_detections_per_msg': np.mean(trial_n_detections_list) if trial_n_detections_list else np.nan
#                     }
                    
#                     trial_summary_data.append({
#                         'trial_number': current_trial_number,
#                         'trial_start_time_hms': start_time_hms,
#                         'trial_end_time_hms': end_time_hms,
#                         'trial_duration_s': trial_duration_s,
#                         **trial_stats, ### NEW ### - Add the new stats to the output row
#                         'trial_start_time_ros_ns': active_trial_start_timestamp_ns,
#                         'trial_end_time_ros_ns': trial_end_timestamp_ns
#                     })
#                     print(f"Info (CSV row {index + 2}): Trial {current_trial_number} recorded. Duration: {trial_duration_s:.3f}s")
#                     current_trial_number += 1
                
#                 # Reset for the next trial
#                 active_trial_start_timestamp_ns = None
#                 last_start_signal_timestamp_ns = None 
#                 trial_all_ranges = []
#                 trial_n_detections_list = []
            
#             else: 
#                 print(f"Warning (CSV row {index + 2}): 'researcher-trial-end' signal occurred, but no trial is currently active. Ignoring.")

#     if active_trial_start_timestamp_ns is not None:
#         print(f"Warning: End of CSV reached, but trial {current_trial_number} did not have a corresponding 'researcher-trial-end' event.")
    
#     ### MODIFIED ### - Add new column names to the output DataFrame
#     output_df_columns = [
#         'trial_number', 
#         'trial_start_time_hms', 'trial_end_time_hms', 'trial_duration_s',
#         'min_range_in_trial', 'max_range_in_trial', 'mean_range_in_trial',
#         'min_n_detections_per_msg', 'max_n_detections_per_msg', 'mean_n_detections_per_msg',
#         'trial_start_time_ros_ns', 'trial_end_time_ros_ns'
#     ]
#     output_df = pd.DataFrame(trial_summary_data, columns=output_df_columns)
    
#     try:
#         output_csv_path.parent.mkdir(parents=True, exist_ok=True)
#         output_df.to_csv(output_csv_path, index=False)
#         print(f"Trial analysis with detection summaries successfully saved to '{output_csv_path}'")
#     except Exception as e:
#         print(f"Error writing output CSV to '{output_csv_path}': {e}")

# def main():
#     # This function remains unchanged
#     parser = argparse.ArgumentParser(
#         description="Analyzes trial start/end times and summarizes detection data from a Joy event CSV file."
#     )
#     parser.add_argument("input_csv", type=Path, help="Path to the input CSV file.")
#     parser.add_argument("output_csv", type=Path, help="Path to save the trial analysis results CSV file.")
#     args = parser.parse_args()

#     analyze_trial_events(args.input_csv, args.output_csv)

# if __name__ == '__main__':
#     main()