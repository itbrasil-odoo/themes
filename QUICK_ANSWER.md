# Quick Answer: Adding 19.0 Branch to Your Fork

**Problem**: Branch 19.0 has been added to the official repository, how do I add this branch to my fork?

**Quick Solution**: Use our automated script:

```bash
# One command to sync the 19.0 branch
./scripts/sync_branch.sh 19.0 https://github.com/OFFICIAL-REPO-OWNER/themes.git
```

## What This Does

1. Adds the official repository as an "upstream" remote
2. Fetches the 19.0 branch from upstream
3. Creates a local 19.0 branch
4. Pushes it to your fork on GitHub

## Manual Alternative

If you prefer manual commands:

```bash
git remote add upstream https://github.com/OFFICIAL-REPO-OWNER/themes.git
git fetch upstream
git checkout -b 19.0 upstream/19.0
git push -u origin 19.0
```

## More Information

- **Complete Guide**: [BRANCH_SYNC.md](BRANCH_SYNC.md) - Detailed documentation with troubleshooting
- **Specific Example**: [ADD_19_BRANCH.md](ADD_19_BRANCH.md) - Step-by-step for the 19.0 branch
- **Script**: [scripts/sync_branch.sh](scripts/sync_branch.sh) - Automated solution

## Important Notes

- Replace `OFFICIAL-REPO-OWNER` with the actual owner of the upstream repository
- This process works for any branch, not just 19.0
- You only need to set up the upstream remote once
- The script includes error checking and colored output for easier use

---

**TL;DR**: Run `./scripts/sync_branch.sh 19.0 UPSTREAM_URL` to automatically sync the 19.0 branch to your fork.