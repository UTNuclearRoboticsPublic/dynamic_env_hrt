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
```
python3 bag_to_csv.py --config ../config/bagfile_analysis.yaml --output ../data/analysis_test.csv ../bags/dryrun/
```