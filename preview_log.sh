#!/bin/bash
# ============================================
# Log Viewer Script
# --------------------------------------------
# Reads a log file for a given date and prints
# each line with color-coded log levels.
#
# Usage:
#   ./preview_logs.sh [YYYY-MM-DD]
#
# If no date is provided, today's date is used.
# ============================================

# Read the first argument as the date
DATE=$1

# Directory where log files are stored
LOG_DIR="./logs"

# If no date argument is provided, default to today
if [[ -z "$DATE" ]]; then
  DATE=$(date +"%Y%m%d")
fi

# Construct the full log file path
LOG_FILE="${LOG_DIR}/${DATE}.log"

# Exit if the log file does not exist
if [[ ! -f "$LOG_FILE" ]]; then
  echo "$LOG_FILE doesn't exist"
  exit 1
fi

# --------------------------------------------
# Function: color_log
# --------------------------------------------
# Prints a log line in a color based on log level
# INFO     -> Blue
# SUCCESS  -> Green
# WARNING  -> Yellow
# ERROR    -> Red
# Default  -> Gray
# --------------------------------------------
color_log() {
    local line="$1"

    if [[ "$line" == *"[INFO]"* ]]; then
        echo -e "\033[1;34m$line\033[0m"
    elif [[ "$line" == *"[SUCCESS]"* ]]; then
        echo -e "\033[1;32m$line\033[0m"
    elif [[ "$line" == *"[WARNING]"* ]]; then
        echo -e "\033[1;93m$line\033[0m"
    elif [[ "$line" == *"[ERROR]"* ]]; then
        echo -e "\033[1;31m$line\033[0m"
    else
        # Lines without a known log level
        echo -e "\033[1;30m$line\033[0m"
    fi
}

# --------------------------------------------
# Read the log file line by line and color it
# --------------------------------------------
while IFS= read -r line; do
    color_log "$line"
done < "$LOG_FILE"
