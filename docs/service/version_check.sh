#!/bin/bash

echo "----------------------------------------"
echo "Version Check Script"
echo "Version: 0.0.3 (2025-01-12)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2025 Bence Damokos"
echo "----------------------------------------"

# Function to get the latest release tag
get_latest_release() {
    local repo="$1"
    local api_url="https://api.github.com/repos/bdamokos/$repo/releases/latest"
    
    # Add user agent to avoid 403 errors
    local response=$(curl -sL \
        -H "Accept: application/vnd.github.v3+json" \
        -H "User-Agent: rpi-display-version-check" \
        "$api_url")
    
    # Check for rate limit
    if echo "$response" | grep -q "API rate limit exceeded"; then
        logger "Rate limited. Using git tags instead..."
        git fetch --tags > /dev/null 2>&1
        local tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "none")
        logger "Found tag: $tag"
        echo "$tag"
        return
    fi
    
    # Extract version from response (compatible with both BSD and GNU grep)
    local latest_release=$(echo "$response" | grep -o '"tag_name": "[^"]*"' | cut -d'"' -f4)
    
    if [ -z "$latest_release" ]; then
        logger "Could not fetch release info. Using git tags instead..."
        git fetch --tags > /dev/null 2>&1
        local tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "none")
        logger "Found tag: $tag"
        echo "$tag"
    else
        logger "Found release: $latest_release"
        echo "$latest_release"
    fi
}

# Function to get the current version
get_current_version() {
    local repo_path="$1"
    cd "$repo_path"
    local tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "none")
    logger "Current version: $tag"
    echo "$tag"
}

# Function for consistent logging
logger() {
    echo "$1" >&2  # Send to stderr so it doesn't interfere with version output
}

# Function to check if update is needed
check_update_needed() {
    local repo_path="$1"
    local repo_name="$2"
    local update_mode="$3"
    
    cd "$repo_path"
    
    case "$update_mode" in
        "none")
            logger "Updates disabled"
            return 1
            ;;
        "releases")
            local current_version=$(get_current_version "$repo_path")
            local latest_release=$(get_latest_release "$repo_name")
            
            if [ -z "$latest_release" ] || [ "$latest_release" = "none" ]; then
                logger "Could not fetch release information"
                return 1
            fi
            
            if [ "$current_version" != "$latest_release" ]; then
                logger "Update available: $current_version -> $latest_release"
                return 0
            else
                logger "Already at latest release: $current_version"
                return 1
            fi
            ;;
        "main")
            # Try to fetch without auth first
            if ! git fetch -q origin main 2>/dev/null; then
                # If fetch fails, try with https
                git remote set-url origin https://github.com/bdamokos/"$repo_name".git
                git fetch -q origin main
            fi
            
            if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
                logger "Updates available from main branch"
                return 0
            else
                logger "Already up to date with main branch"
                return 1
            fi
            ;;
        *)
            logger "Invalid update mode: $update_mode"
            return 1
            ;;
    esac
}

# Function to perform the update
perform_update() {
    local repo_path="$1"
    local repo_name="$2"
    local update_mode="$3"
    
    cd "$repo_path"
    
    case "$update_mode" in
        "none")
            return 0
            ;;
        "releases")
            local latest_release=$(get_latest_release "$repo_name")
            if [ -n "$latest_release" ] && [ "$latest_release" != "none" ]; then
                logger "Updating to release $latest_release..."
                git fetch --tags
                git checkout "$latest_release"
                return $?
            fi
            return 1
            ;;
        "main")
            logger "Updating to latest main branch..."
            # Ensure we're using https
            git remote set-url origin https://github.com/bdamokos/"$repo_name".git
            git reset --hard origin/main
            git pull -v origin main
            return $?
            ;;
        *)
            return 1
            ;;
    esac
}

# Main section to handle direct function calls
if [ "$1" = "check_update_needed" ] && [ $# -eq 4 ]; then
    check_update_needed "$2" "$3" "$4"
    exit $?
elif [ "$1" = "perform_update" ] && [ $# -eq 4 ]; then
    perform_update "$2" "$3" "$4"
    exit $?
fi 