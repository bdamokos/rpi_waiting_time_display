#!/bin/sh
# Bound legacy file logs before the display starts. New systemd examples use
# journald, but this also protects existing installations that append to files.

set -u

max_bytes=${DISPLAY_LOG_MAX_BYTES:-10485760}
keep_bytes=${DISPLAY_LOG_KEEP_BYTES:-1048576}

case "$max_bytes:$keep_bytes" in
    *[!0-9:]*|:*)
        echo "Invalid display log size configuration" >&2
        exit 2
        ;;
esac

if [ "$keep_bytes" -gt "$max_bytes" ]; then
    keep_bytes=$max_bytes
fi

if [ "$#" -eq 0 ]; then
    set -- /var/log/display/display.out /var/log/display/display.err /var/log/display_service.log
fi

for log_file in "$@"; do
    [ -f "$log_file" ] || continue
    size=$(wc -c < "$log_file") || continue
    [ "$size" -gt "$max_bytes" ] || continue

    previous="${log_file}.previous"
    temporary="${previous}.tmp"
    if tail -c "$keep_bytes" "$log_file" > "$temporary" && mv "$temporary" "$previous"; then
        : > "$log_file"
        echo "Bounded oversized log $log_file ($size bytes)" >&2
    else
        rm -f "$temporary"
        echo "Could not bound oversized log $log_file" >&2
    fi
done
