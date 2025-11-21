#!/bin/bash
# Calculate the next revision number for a given upstream version
# Finds all git tags matching v<upstream-version>+<N> or v<upstream-version>+<N>_pre
# Returns the next N value (highest N + 1), or 1 if no matching tags exist
#
# Usage: calculate-revision.sh <upstream-version>

set -euo pipefail

UPSTREAM_VERSION="${1:-}"

if [ -z "$UPSTREAM_VERSION" ]; then
    echo "Error: Upstream version is required" >&2
    echo "Usage: $0 <upstream-version>" >&2
    exit 1
fi

# Remove 'v' prefix if present
UPSTREAM_VERSION="${UPSTREAM_VERSION#v}"

# Find all tags matching the pattern: v{version}+{N} or v{version}+{N}_pre
PATTERN="v${UPSTREAM_VERSION}+*"
MATCHING_TAGS=$(git tag -l "$PATTERN" 2>/dev/null || true)

if [ -z "$MATCHING_TAGS" ]; then
    # No matching tags, this is the first build
    echo "1"
    exit 0
fi

# Extract revision numbers from tags and find max
MAX_REVISION=0
while IFS= read -r tag; do
    # Extract the number between '+' and either end of string or '_'
    if [[ $tag =~ \+([0-9]+)(_.*)?$ ]]; then
        REVISION="${BASH_REMATCH[1]}"
        if [ "$REVISION" -gt "$MAX_REVISION" ]; then
            MAX_REVISION="$REVISION"
        fi
    fi
done <<< "$MATCHING_TAGS"

# Return next revision number
NEXT_REVISION=$((MAX_REVISION + 1))
echo "$NEXT_REVISION"
