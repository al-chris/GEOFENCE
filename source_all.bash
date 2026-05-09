#!/bin/bash
# source_all.bash: Sources ROS 2, the .venv, and the workspace.

# 1. Source ROS 2
if [ -f "/opt/ros/jazzy/setup.bash" ]; then
    source /opt/ros/jazzy/setup.bash
elif [ -f "/opt/ros/humble/setup.bash" ]; then
    source /opt/ros/humble/setup.bash
else
    # Fallback to any ROS 2 setup if found
    source /opt/ros/*/setup.bash 2>/dev/null
fi

# 2. Source the virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# 3. Source the workspace
if [ -f "install/setup.bash" ]; then
    source install/setup.bash
fi

# 4. Export PYTHONPATH to bridge the venv and ROS 2
# This ensures nodes using #!/usr/bin/python3 can still see venv packages.
export PYTHONPATH=$PYTHONPATH:$(pwd)/.venv/lib/python3.12/site-packages

echo "Environment sourced successfully."
