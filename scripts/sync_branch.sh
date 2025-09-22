#!/bin/bash

# Automated script to sync new branches from upstream repository
# Usage: ./sync_branch.sh <branch_name> [upstream_url]

set -e  # Exit on any error

BRANCH_NAME="$1"
UPSTREAM_URL="${2:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if branch name is provided
if [ -z "$BRANCH_NAME" ]; then
    print_error "Branch name is required!"
    echo "Usage: $0 <branch_name> [upstream_url]"
    echo "Example: $0 19.0"
    echo "Example: $0 19.0 https://github.com/ORIGINAL-OWNER/themes.git"
    exit 1
fi

print_status "Starting branch synchronization for: $BRANCH_NAME"

# Check if git is available
if ! command -v git &> /dev/null; then
    print_error "Git is not installed or not in PATH"
    exit 1
fi

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    print_error "Not in a git repository"
    exit 1
fi

# Check if upstream remote exists
if ! git remote | grep -q "^upstream$"; then
    if [ -z "$UPSTREAM_URL" ]; then
        print_error "Upstream remote not found and no upstream URL provided"
        echo "Please provide the upstream repository URL:"
        echo "$0 $BRANCH_NAME https://github.com/ORIGINAL-OWNER/themes.git"
        exit 1
    fi
    
    print_status "Adding upstream remote: $UPSTREAM_URL"
    git remote add upstream "$UPSTREAM_URL"
else
    print_status "Upstream remote already exists"
fi

# Fetch from upstream
print_status "Fetching branches from upstream..."
git fetch upstream

# Check if the branch exists on upstream
if ! git ls-remote --heads upstream | grep -q "refs/heads/$BRANCH_NAME$"; then
    print_error "Branch '$BRANCH_NAME' does not exist on upstream repository"
    echo "Available upstream branches:"
    git ls-remote --heads upstream | sed 's/.*refs\/heads\//  - /'
    exit 1
fi

# Check if local branch already exists
if git branch | grep -q "^[* ]*$BRANCH_NAME$"; then
    print_warning "Local branch '$BRANCH_NAME' already exists"
    read -p "Do you want to reset it to match upstream? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Deleting existing local branch '$BRANCH_NAME'"
        git branch -D "$BRANCH_NAME" 2>/dev/null || true
    else
        print_status "Keeping existing local branch"
        exit 0
    fi
fi

# Create and checkout the new branch from upstream
print_status "Creating local branch '$BRANCH_NAME' from upstream/$BRANCH_NAME"
git checkout -b "$BRANCH_NAME" "upstream/$BRANCH_NAME"

# Push to origin
print_status "Pushing branch '$BRANCH_NAME' to origin"
if git push -u origin "$BRANCH_NAME"; then
    print_status "Successfully synced branch '$BRANCH_NAME'"
    echo
    echo "Branch '$BRANCH_NAME' has been successfully added to your fork!"
    echo "You can now work with this branch using standard git commands."
else
    print_error "Failed to push branch to origin"
    exit 1
fi

# Show final status
echo
print_status "Summary:"
echo "  - Local branch '$BRANCH_NAME' created from upstream"
echo "  - Branch pushed to your fork with tracking set up"
echo "  - You can now use 'git push' to push future changes"
echo
echo "To keep this branch updated with upstream:"
echo "  git checkout $BRANCH_NAME"
echo "  git pull upstream $BRANCH_NAME"
echo "  git push origin $BRANCH_NAME"