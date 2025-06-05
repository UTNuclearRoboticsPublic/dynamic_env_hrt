# dynamic_env_hrt
Supporting materials for human-robot teaming experiments in dynamic environments.

# Setup & Installation
## Create workspace and clone repository

## Create virtual environment
```
mamba env create -f hrt_env.yml
```

## Install ROS dependencies

# Usage

## Analyzing bagfiles

Put relevant events into a CSV spreadsheet
```
python3 bag_to_csv.py --config ../config/bagfile_analysis.yaml --output ../data/cohort-1-raw.csv ../bags/cohort-1/
python3 bag_to_csv.py --config ../config/bagfile_analysis.yaml --output ../data/cohort-2-raw.csv ../bags/cohort-2/
python3 bag_to_csv.py --config ../config/bagfile_analysis.yaml --output ../data/cohort-3-raw.csv ../bags/cohort-3/
python3 bag_to_csv.py --config ../config/bagfile_analysis.yaml --output ../data/cohort-4-raw.csv ../bags/cohort-4/
```

Analyze the spreadsheets
```
python3 analyze_csv.py ../data/cohort-4-raw.csv  ../data/cohort-4-processed.csv
```