#!/usr/bin/env -S bash --login
set -euo pipefail
# This wrapper script accepts named arguments and calls run.sh with positional arguments

# Get current location of script
basedir=$(dirname "$(readlink -f "$0")")

# Initialize variables
source=""
region=""

# Parse named arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --source)
            source="$2"
            shift 2
            ;;
        --region)
            region="$2"
            shift 2
            ;;
        *)
            echo "Error: Unknown argument '$1'"
            echo "Usage: $0 --source <value> [--region <value>]"
            exit 1
            ;;
    esac
done

# Validate all required arguments are provided
if [[ -z "$source" ]]; then
    echo "Error: --source is required"
    exit 1
fi


# Call run.sh with positional arguments
if [[ -n "$region" ]]; then
    "${basedir}/run.sh" "$source" "$region"
else
    "${basedir}/run.sh" "$source"
fi
