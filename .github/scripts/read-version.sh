#!/bin/bash
# Read version from VERSION file
# Sets version and tag_version in GitHub output

set -e

VERSION=$(cat VERSION | tr -d '\n\r ')
# For daemon, version and tag_version are the same
TAG_VERSION="$VERSION"

echo "version=$VERSION" >> "$GITHUB_OUTPUT"
echo "tag_version=$TAG_VERSION" >> "$GITHUB_OUTPUT"
echo "Version from VERSION file: $VERSION (tag version: $TAG_VERSION)"
