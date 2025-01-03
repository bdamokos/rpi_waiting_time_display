#!/bin/bash

echo "----------------------------------------"
echo "Version Check Script"
echo "Version: 0.0.2 (2025-01-03)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2025 Bence Damokos"
echo "----------------------------------------"

# Function to get the latest release tag
get_latest_release() {
    local repo="$1"
    local latest_release=$(curl -s "https://api.github.com/repos/bdamokos/$repo/releases/latest" | grep -oP '"tag_name": "\K[^"]+')
    echo "$latest_release"
}

# Function to get the current version
get_current_version() {
    local repo_path="$1"
    cd "$repo_path"
    git describe --tags --abbrev=0 2>/dev/null || echo "none"
}

# Function to check if update is needed
check_update_needed() {
    local repo_path="$1"
    local repo_name="$2"
    local update_mode="$3"
    
    cd "$repo_path"
    
    case "$update_mode" in
        "none")
            echo "Updates disabled"
            return 1
            ;;
        "releases")
            local current_version=$(get_current_version "$repo_path")
            local latest_release=$(get_latest_release "$repo_name")
            
            if [ -z "$latest_release" ]; then
                echo "Could not fetch latest release information"
                return 1
            fi
            
            if [ "$current_version" != "$latest_release" ]; then
                echo "Update available: $current_version -> $latest_release"
                return 0
            else
                echo "Already at latest release: $current_version"
                return 1
            fi
            ;;
        "main")
            git fetch -q origin main
            if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
                echo "Updates available from main branch"
                return 0
            else
                echo "Already up to date with main branch"
                return 1
            fi
            ;;
        *)
            echo "Invalid update mode: $update_mode"
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
            if [ -n "$latest_release" ]; then
                echo "Updating to release $latest_release..."
                git fetch --tags
                git checkout "$latest_release"
                return $?
            fi
            return 1
            ;;
        "main")
            echo "Updating to latest main branch..."
            git reset --hard origin/main
            git pull -v origin main
            return $?
            ;;
        *)
            return 1
            ;;
    esac
} 