# Branch Synchronization Guide

This guide explains how to add new branches from the official upstream repository to your fork.

## Problem
When a new branch (like 19.0) is added to the official repository, you need to sync it to your fork to keep your repository up-to-date with the latest developments.

## Solution

### Quick Start (Automated Script)

We provide an automated script to simplify this process. You can use it to sync any branch from upstream:

```bash
# Make the script executable (first time only)
chmod +x scripts/sync_branch.sh

# Sync the 19.0 branch (replace with actual upstream URL)
./scripts/sync_branch.sh 19.0 https://github.com/ORIGINAL-OWNER/themes.git

# Or if upstream remote is already configured:
./scripts/sync_branch.sh 19.0
```

### Manual Process

If you prefer to do it manually or want to understand the process better, follow these steps:

### Step 1: Add the Upstream Remote

If you haven't already added the upstream remote, you need to add it first. The upstream remote points to the original repository that you forked from.

```bash
# Add the upstream remote (replace with the actual upstream repository URL)
git remote add upstream https://github.com/ORIGINAL-OWNER/themes.git

# Verify the remote was added
git remote -v
```

You should see something like:
```
origin    https://github.com/YOUR-USERNAME/themes.git (fetch)
origin    https://github.com/YOUR-USERNAME/themes.git (push)
upstream  https://github.com/ORIGINAL-OWNER/themes.git (fetch)
upstream  https://github.com/ORIGINAL-OWNER/themes.git (push)
```

### Step 2: Fetch All Branches from Upstream

Fetch all the latest branches and commits from the upstream repository:

```bash
# Fetch all branches from upstream
git fetch upstream

# List all available branches (including remote ones)
git branch -a
```

### Step 3: Create and Push the 19.0 Branch

Once you've fetched the upstream branches, you can create the 19.0 branch locally and push it to your fork:

```bash
# Create and checkout the 19.0 branch from upstream
git checkout -b 19.0 upstream/19.0

# Push the new branch to your fork
git push origin 19.0

# Set up tracking so future pushes work with just 'git push'
git push -u origin 19.0
```

### Step 4: Verify the Branch

Verify that the branch was created successfully:

```bash
# Check current branch
git branch

# Check remote branches
git branch -r

# Verify the branch exists on your fork (GitHub web interface)
```

## Alternative Method: Direct Fetch and Push

If you prefer a more direct approach without switching branches:

```bash
# Fetch the specific branch from upstream
git fetch upstream 19.0:19.0

# Push the branch to your fork
git push origin 19.0
```

## Keeping the Branch Updated

To keep the 19.0 branch updated with upstream changes:

```bash
# Switch to the 19.0 branch
git checkout 19.0

# Pull latest changes from upstream
git pull upstream 19.0

# Push updates to your fork
git push origin 19.0
```

## Troubleshooting

### Error: "upstream/19.0" does not exist
This means the 19.0 branch doesn't exist in the upstream repository yet, or you haven't fetched it properly.

**Solution:**
```bash
# Re-fetch from upstream
git fetch upstream

# List all upstream branches to verify
git branch -r | grep upstream
```

### Error: "fatal: A branch named '19.0' already exists"
This means you already have a local 19.0 branch.

**Solution:**
```bash
# Delete the existing local branch (if safe to do so)
git branch -D 19.0

# Then create the branch again from upstream
git checkout -b 19.0 upstream/19.0
```

### Error: Permission denied when pushing
Make sure you have write access to your fork and are authenticated properly.

**Solution:**
```bash
# Verify your remote URLs
git remote -v

# Make sure you're pushing to your fork, not the upstream
git push origin 19.0
```

## Best Practices

1. **Always fetch before creating branches** to ensure you have the latest updates
2. **Use descriptive branch names** if you're creating feature branches based on 19.0
3. **Regularly sync your fork** to stay up-to-date with upstream changes
4. **Test your setup** with a simple branch first if you're unsure

## Summary

The key steps to add the 19.0 branch to your fork are:
1. Add upstream remote (if not already done)
2. Fetch branches from upstream
3. Create local 19.0 branch from upstream/19.0
4. Push the branch to your fork

This process ensures your fork stays synchronized with the official repository and gives you access to all the latest branches and features.