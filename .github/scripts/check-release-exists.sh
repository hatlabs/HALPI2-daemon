#!/bin/bash
# Check if a release exists and set output flags
# Usage: check-release-exists.sh <VERSION> [RELEASE_TYPE]
# RELEASE_TYPE: "prerelease" (default), "draft", or "stable"

set -e

VERSION="${1:?Version required}"
RELEASE_TYPE="${2:-prerelease}"

if [ -z "$VERSION" ]; then
  echo "Error: VERSION argument required"
  exit 1
fi

case "$RELEASE_TYPE" in
  prerelease)
    # Check if published (non-prerelease) release with same or higher version exists
    HIGHEST_STABLE=$(gh release list --limit 100 --json tagName,isPrerelease,isDraft \
      --jq '.[] | select(.isDraft == false and .isPrerelease == false) | .tagName' | \
      sed 's/^v//' | sort -V | tail -n1)

    if [ -n "$HIGHEST_STABLE" ]; then
      echo "Found highest stable release: v${HIGHEST_STABLE}"
      # Compare versions using dpkg --compare-versions
      # Strip Debian revision from VERSION for comparison (0.2.0-1 → 0.2.0)
      # Note: ${VERSION%-*} is safe - if VERSION has no dash, it returns VERSION unchanged
      if dpkg --compare-versions "${VERSION%-*}" le "$HIGHEST_STABLE"; then
        echo "action=skip" >> "$GITHUB_OUTPUT"
        echo "⏭️  Stable release v${HIGHEST_STABLE} >= v${VERSION%-*} - skipping pre-release"
        exit 0
      fi
    fi
    echo "action=create" >> "$GITHUB_OUTPUT"
    echo "✅ No published release with same or higher version - will create pre-release v${VERSION%-*}"
    ;;

  draft)
    # Check if release exists (any kind)
    if gh release view "v$VERSION" &>/dev/null; then
      IS_DRAFT=$(gh release view "v$VERSION" --json isDraft --jq '.isDraft')
      if [ "$IS_DRAFT" = "true" ]; then
        echo "skip=false" >> "$GITHUB_OUTPUT"
        echo "delete_existing=true" >> "$GITHUB_OUTPUT"
        echo "Existing draft release found - will delete and recreate"
      else
        echo "skip=true" >> "$GITHUB_OUTPUT"
        echo "delete_existing=false" >> "$GITHUB_OUTPUT"
        echo "Published release v$VERSION already exists - skipping"
      fi
    else
      echo "skip=false" >> "$GITHUB_OUTPUT"
      echo "delete_existing=false" >> "$GITHUB_OUTPUT"
      echo "No existing release found"
    fi
    ;;

  stable)
    # For stable releases, check if prerelease exists to delete first
    if gh release view "v$VERSION" &>/dev/null; then
      IS_PRERELEASE=$(gh release view "v$VERSION" --json isPrerelease --jq '.isPrerelease')
      if [ "$IS_PRERELEASE" = "true" ]; then
        echo "action=delete" >> "$GITHUB_OUTPUT"
        echo "🗑️  Existing pre-release v$VERSION found - will delete before creating stable"
      else
        echo "action=skip" >> "$GITHUB_OUTPUT"
        echo "⏭️  Published release v$VERSION already exists - skipping"
      fi
    else
      echo "action=create" >> "$GITHUB_OUTPUT"
      echo "✅ No existing release found - will create v$VERSION"
    fi
    ;;

  *)
    echo "Error: Unknown RELEASE_TYPE '$RELEASE_TYPE'. Use 'prerelease', 'draft', or 'stable'"
    exit 1
    ;;
esac
