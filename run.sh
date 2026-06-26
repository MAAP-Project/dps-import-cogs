#!/usr/bin/env -S bash --login
set -euo pipefail
# This script is the one that is called by the DPS.
# Use this script to prepare input paths for any files
# that are downloaded by the DPS and outputs that are
# required to be persisted

# Get current location of build script
basedir=$(dirname "$(readlink -f "$0")")

# Create output directory to store outputs.
# The name is output as required by the DPS.
# Note how we dont provide an absolute path
# but instead a relative one as the DPS creates
# a temp working directory for our code.

mkdir -p output


# DPS downloads all files provided as inputs to
# this directory called input.
# In our example the image will be downloaded here.
INPUT_DIR=input
OUTPUT_DIR=output

source="$1"
region="${2:-}"
include_extensions="${3:-}"
exclude_extensions="${4:-}"

# Call the script using the absolute paths
# Use the updated environment when calling 'uv run'
# This lets us run the same way in a Terminal as in DPS
# Any output written to the stdout and stderr streams will be automatically captured and placed in the output dir

# unset PROJ env vars
unset PROJ_LIB
unset PROJ_DATA

# Build command arguments
args=(
    --source="${source}"
    --output_dir="${OUTPUT_DIR}"
)

# Only add optional parameters if provided. Extension arguments may be
# intentionally empty, so check the number of positional arguments for those.
if [ -n "$region" ]; then
    args+=(--region="${region}")
fi

if [ "$#" -ge 3 ]; then
    args+=(--include-extensions="${include_extensions}")
fi

if [ "$#" -ge 4 ]; then
    args+=(--exclude-extensions="${exclude_extensions}")
fi

UV_PROJECT=${basedir} uv run --no-dev ${basedir}/main.py "${args[@]}"
