# Adding the 19.0 Branch - Quick Example

This is a specific example for adding the 19.0 branch to your fork when it becomes available in the official repository.

## Prerequisites

1. You have a fork of the themes repository
2. You have the repository cloned locally
3. Git is installed and configured

## Method 1: Using the Automated Script

```bash
# Navigate to your local repository
cd your-themes-repository

# Run the sync script (replace UPSTREAM-URL with the actual upstream repository)
./scripts/sync_branch.sh 19.0 https://github.com/UPSTREAM-OWNER/themes.git
```

## Method 2: Manual Git Commands

```bash
# Navigate to your local repository
cd your-themes-repository

# Add upstream remote (if not already added)
git remote add upstream https://github.com/UPSTREAM-OWNER/themes.git

# Fetch all branches from upstream
git fetch upstream

# Create and checkout the 19.0 branch from upstream
git checkout -b 19.0 upstream/19.0

# Push the branch to your fork
git push -u origin 19.0
```

## Verification

After running either method, verify the branch was created:

```bash
# Check that you're on the 19.0 branch
git branch

# Verify the branch exists on your fork
git branch -r | grep origin/19.0

# Check the latest commits
git log --oneline -5
```

## Next Steps

Once you have the 19.0 branch in your fork:

1. You can create feature branches based on it: `git checkout -b feature/my-feature 19.0`
2. Keep it updated with upstream: `git pull upstream 19.0 && git push origin 19.0`
3. Create pull requests targeting the 19.0 branch

## Common Issues

**Error: "upstream/19.0 does not exist"**
- The 19.0 branch hasn't been created in the upstream repository yet
- Double-check the upstream repository URL
- Run `git ls-remote --heads upstream` to see available branches

**Error: "Permission denied"**
- Make sure you're authenticated with GitHub
- Verify you have write access to your fork
- Check that you're pushing to `origin` (your fork), not `upstream`

For more detailed information, see the complete [Branch Synchronization Guide](BRANCH_SYNC.md).