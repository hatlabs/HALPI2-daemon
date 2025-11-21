#!/bin/bash
set -euo pipefail

# Rename packages with distro+component suffix
# Usage: rename-packages.sh --version <debian-version> --distro <distro> --component <component>
#
# This script handles the ARM64 architecture package naming for HALPI2 daemon

VERSION=""
DISTRO=""
COMPONENT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --distro)
            DISTRO="$2"
            shift 2
            ;;
        --component)
            COMPONENT="$2"
            shift 2
            ;;
        *)
            echo "Error: Unknown option $1" >&2
            echo "Usage: $0 --version <debian-version> --distro <distro> --component <component>" >&2
            exit 1
            ;;
    esac
done

if [ -z "$VERSION" ] || [ -z "$DISTRO" ] || [ -z "$COMPONENT" ]; then
    echo "Error: All options are required" >&2
    exit 1
fi

# Package name and architecture
PACKAGE_NAME="halpi2-daemon"
ARCH="arm64"

OLD_NAME="${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
NEW_NAME="${PACKAGE_NAME}_${VERSION}_${ARCH}+${DISTRO}+${COMPONENT}.deb"

if [ -f "$OLD_NAME" ]; then
    echo "Renaming package: $OLD_NAME -> $NEW_NAME"
    mv "$OLD_NAME" "$NEW_NAME"
    echo "Package renamed successfully"
else
    echo "Error: Expected package not found: $OLD_NAME" >&2
    echo "Available .deb files:" >&2
    ls -la *.deb 2>/dev/null || echo "None found" >&2
    exit 1
fi
