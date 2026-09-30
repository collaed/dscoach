# Required GitHub Repository Secrets

Configure these in: Settings → Secrets and variables → Actions

| Secret | Purpose | How to get |
|--------|---------|------------|
| `DEPLOY_SSH_KEY` | SSH private key for deploying to ecb.pm | Generate with `ssh-keygen -t ed25519 -C "github-actions-deploy"`, add public key to `root@ecb.pm:~/.ssh/authorized_keys` |
| `DEPLOY_SSH_KNOWN_HOSTS` | SSH host key for ecb.pm | Run `ssh-keyscan ecb.pm` and paste the output |
| `DB_PASSWORD` | PostgreSQL password for the `coaching` user on ecb.pm | Stored in the `docker run` command that created the postgres container |
| `SECRET_KEY` | Flask session signing key | Generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `SONAR_TOKEN` | SonarCloud analysis upload | https://sonarcloud.io/account/security → Generate Tokens |

## SonarCloud Setup

1. Go to https://sonarcloud.io
2. Import the `eddycollart/coaching-system` repository
3. Choose "With GitHub Actions" as the analysis method
4. The `sonar-project.properties` file is already configured

## Notes

- `GITHUB_TOKEN` is provided automatically by GitHub Actions (no manual setup)
- The deploy job only runs on pushes to `main` (not on PRs)
- Deploy uses SSH to build and restart the Docker container on ecb.pm

## Environment Protection (required)

The deploy job uses `environment: production`. You must create this environment:

1. Go to Settings → Environments → New environment → name it `production`
2. Enable "Required reviewers" → add yourself (`eddycollart`)
3. This forces a manual approval click before every production deploy
4. Quality gates run automatically; deploy waits for your explicit "Approve"

## Rollback Procedure

If a deploy breaks production:

```bash
# Option 1: Revert the commit and push (triggers full CI pipeline, ~3 min)
git revert HEAD --no-edit
git push

# Option 2: SSH in and restart the previous image manually
ssh ecb.pm "docker stop coaching && docker rm coaching"
# Then re-run the docker run command with the previous image tag or rebuild from a known-good commit

# Option 3: Quick fix — docker cp a single patched file
scp src/FIXED_FILE.py ecb.pm:/tmp/FIXED_FILE.py
ssh ecb.pm "docker cp /tmp/FIXED_FILE.py coaching:/app/src/FIXED_FILE.py && docker restart coaching && rm /tmp/FIXED_FILE.py"
```

**Known latency:** Option 1 takes ~3 minutes (full CI). Option 2 is ~30s (manual SSH). Option 3 is ~10s (single file patch).
