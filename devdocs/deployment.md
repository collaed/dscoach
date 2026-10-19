# deployment.md — Deployment & Operations (DSCoaching)

## Production: Docker on ecb.pm

### Infrastructure

| Component | Detail |
|-----------|--------|
| VPS | ecb.pm (178.104.101.76), Hetzner |
| Container | `coaching` (image `coaching-coaching:latest`) |
| Database | Shared `postgres` container (PostgreSQL 16), DB name `coaching`, user `coaching` |
| Networks | `db` (postgres access) + `web` (Caddy access) |
| Caddy site | `/opt/caddy/sites/coaching.caddy` → `reverse_proxy coaching:8000` |
| URL | `https://dscoaching.ecb.pm/` |
| Volume | `coaching-data` mounted at `/data/attachments` |

### Seeded Accounts

| Username | Password | Role |
|----------|----------|------|
| `ecb` | `ecbF3T` | Admin + Coach |
| `Kitsune` | `Goddess` | Coach |
| `severin` | `ecbS3V` | Coachee (under Kitsune) |

### Environment Variables (set in `docker run`)

| Variable | Purpose |
|----------|---------|
| `DB_ENGINE` | `postgresql` |
| `DB_HOST` | `postgres` (container name on `db` network) |
| `DB_PORT` | `5432` |
| `DB_USERNAME` | `coaching` |
| `DB_PASSWORD` | PostgreSQL password (stored in GitHub Secrets for CI) |
| `DB_NAME` | `coaching` |
| `SECRET_KEY` | Flask session signing key (stored in GitHub Secrets for CI) |
| `PORT` | `8000` |

### Deploy Flow (automated via CI)

```
push to main → quality gates pass → manual approval → SSH into ecb.pm → build image → replace container → health check
```

The CI pipeline (`.github/workflows/ci.yml`):
1. Builds a tarball of `Dockerfile`, `src/`, `lib/`, `static/`
2. SCPs it to ecb.pm
3. Runs `docker build` on ecb.pm
4. Stops and removes the old container
5. Starts a new container with env vars from GitHub Secrets
6. Connects the container to the `web` network
7. Health checks `https://dscoaching.ecb.pm/login`

### Manual Deploy

```bash
# 1. Build tarball locally (exclude caches)
cd /home/collaed/projects/esc_site
tar czf /tmp/coaching-deploy.tar.gz --exclude='__pycache__' --exclude='*.pyc' Dockerfile src/ lib/ static/

# 2. Transfer to ecb.pm
scp /tmp/coaching-deploy.tar.gz ecb.pm:/tmp/coaching-deploy.tar.gz

# 3. Build image on ecb.pm
ssh ecb.pm "mkdir -p /tmp/coaching-build && cd /tmp/coaching-build && tar xzf /tmp/coaching-deploy.tar.gz && docker build -t coaching-coaching . && rm -rf /tmp/coaching-build /tmp/coaching-deploy.tar.gz"

# 4. Replace container
ssh ecb.pm "docker stop coaching && docker rm coaching"
ssh ecb.pm 'docker run -d --name coaching \
  --network db \
  -e DB_ENGINE=postgresql \
  -e DB_HOST=postgres \
  -e DB_PORT=5432 \
  -e DB_USERNAME=coaching \
  -e DB_PASSWORD=<password> \
  -e DB_NAME=coaching \
  -e SECRET_KEY=<secret-key> \
  -e PORT=8000 \
  --restart unless-stopped \
  coaching-coaching'
ssh ecb.pm "docker network connect web coaching"

# 5. Verify
ssh ecb.pm "docker logs coaching --tail 10"
curl -sI https://dscoaching.ecb.pm/ | head -5

# 6. Cleanup
rm /tmp/coaching-deploy.tar.gz
```

### Quick Patch (single file, no rebuild)

```bash
scp src/FIXED_FILE.py ecb.pm:/tmp/FIXED_FILE.py
ssh ecb.pm "docker cp /tmp/FIXED_FILE.py coaching:/app/src/FIXED_FILE.py && docker restart coaching && rm /tmp/FIXED_FILE.py"
```

Note: code inside the container is **not volume-mounted** — `docker cp` overrides are ephemeral and lost on the next full rebuild. Use this only for emergency patches.

### Rollback

```bash
# Option 1: Git revert (triggers full CI, ~3 min)
git revert HEAD --no-edit && git push

# Option 2: Quick fix — docker cp a single patched file (~10s)
scp src/FIXED_FILE.py ecb.pm:/tmp/FIXED_FILE.py
ssh ecb.pm "docker cp /tmp/FIXED_FILE.py coaching:/app/src/FIXED_FILE.py && docker restart coaching && rm /tmp/FIXED_FILE.py"

# Option 3: Rebuild from a known-good commit (~30s)
git checkout <good-commit> -- src/ lib/ static/ Dockerfile
# Then follow the manual deploy steps above
```

### Schema Migrations

`metadata.create_all()` only creates missing tables — it won't ALTER existing ones. For column additions:

```bash
# Add a column manually:
ssh ecb.pm "docker exec postgres psql -U coaching coaching -c 'ALTER TABLE coachee ADD COLUMN login_count INTEGER DEFAULT 0;'"

# Then restart the app container:
ssh ecb.pm "docker restart coaching"
```

### Quick Checks

```bash
# Container status
ssh ecb.pm "docker ps --filter name=coaching"

# Recent logs
ssh ecb.pm "docker logs coaching --tail 20"

# DB query
ssh ecb.pm "docker exec postgres psql -U coaching coaching -c 'SELECT username, is_admin FROM coach;'"

# Caddy config
ssh ecb.pm "cat /opt/caddy/sites/coaching.caddy"
```

## Local Development

```bash
# SQLite (no external DB needed)
export DB_ENGINE=sqlite SECRET_KEY=dev
flask --app src/app run --debug --no-reload
# Visit http://127.0.0.1:5000/setup (first time)

# Or with local PostgreSQL via Docker Compose
docker-compose up  # starts app + postgres
# Uses DATABASE_URL=postgresql+psycopg2://coaching:coaching_pwd_2026@postgres:5432/coaching
# Visit http://localhost:8080
```

## CI Pipeline

Defined in `.github/workflows/ci.yml`:

| Step | Tool | What it checks |
|------|------|---------------|
| 1 | ruff check | Lint errors, import sorting |
| 2 | ruff format --check | Code formatting |
| 3 | bandit -ll | Security issues (medium+ severity) |
| 4 | mypy | Type errors |
| 5 | pytest --cov | 81 tests + coverage report |
| 6 | SonarCloud | Code smells, coverage dashboard |
| 7 | Manual approval | Environment protection gate |
| 8 | SSH deploy | Build + restart container on ecb.pm |
| 9 | Health check | Verify /login returns 200 |

### Running CI locally

```bash
pip install -r requirements-dev.txt
ruff check src/ tests/
ruff format --check src/ tests/
bandit -r src/ -x src/templates/,src/db.py,src/db_pg.py,src/server_docker.py -ll
mypy src/ --ignore-missing-imports --exclude 'db\.py|db_pg\.py|server_docker\.py'
DB_ENGINE=sqlite SECRET_KEY=test pytest --cov=src
```

### Required GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `DEPLOY_SSH_KEY` | SSH private key for root@ecb.pm |
| `DEPLOY_SSH_KNOWN_HOSTS` | SSH host key for ecb.pm |
| `DB_PASSWORD` | PostgreSQL password for the `coaching` user |
| `SECRET_KEY` | Flask session signing key |
| `SONAR_TOKEN` | SonarCloud upload |

### Environment Setup

Create `production` environment in GitHub Settings → Environments with "Required reviewers" enabled.

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Connection refused` on deploy | Container didn't start or isn't on `web` network | Check `docker logs coaching --tail 20`, verify `docker network connect web coaching` |
| `ModuleNotFoundError` | New import not vendored in `lib/` | Vendor the dependency or install in Dockerfile |
| `500 on first request` | `init_db()` failing | Check `docker logs coaching --tail 20` for SQL error |
| `OperationalError` on PG | Dialect-specific SQL slipped in | Use `_rand_func()`, `_now_func()`, or Python date math |
| Health check fails after deploy | Container slow to start or Caddy not routing | SSH in, check `docker ps`, check Caddy config |
