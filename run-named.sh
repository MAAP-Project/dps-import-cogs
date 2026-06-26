#!/usr/bin/env -S bash --login
set -euo pipefail
# This wrapper script accepts named arguments and calls run.sh with positional arguments

# Get current location of script
basedir=$(dirname "$(readlink -f "$0")")

# Initialize variables
source=""
region=""
include_extensions=""
exclude_extensions=""
include_extensions_set=false
exclude_extensions_set=false

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
        --include-extensions)
            include_extensions="$2"
            include_extensions_set=true
            shift 2
            ;;
        --exclude-extensions)
            exclude_extensions="$2"
            exclude_extensions_set=true
            shift 2
            ;;
        *)
            echo "Error: Unknown argument '$1'"
            echo "Usage: $0 --source <value> [--region <value>] [--include-extensions <value>] [--exclude-extensions <value>]"
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
args=("$source")

if [[ -n "$region" || "$include_extensions_set" == true || "$exclude_extensions_set" == true ]]; then
    args+=("$region")
fi

if [[ "$include_extensions_set" == true || "$exclude_extensions_set" == true ]]; then
    args+=("$include_extensions")
fi

if [[ "$exclude_extensions_set" == true ]]; then
    args+=("$exclude_extensions")
fi

"${basedir}/run.sh" "${args[@]}"
