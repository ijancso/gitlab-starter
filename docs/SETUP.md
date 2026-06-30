# SETUP — step-by-step

This guide takes you from nothing to a green, multi-stage pipeline running on
your own self-hosted GitLab, then publishes the project to GitHub as a
portfolio piece.

It has four parts:

- **Part 0 — Prerequisites**
- **Part 1 — Stand up a local GitLab CE + Runner** (this is "step 0")
- **Part 2 — Run the Python pipeline** (this is "option B")
- **Part 3 — Publish to GitHub as portfolio**
- **Part 4 — Where to go next**
- **Troubleshooting**

---

## Part 0 — Prerequisites

- **Docker** and the **Docker Compose plugin** (`docker compose version` works).
- At least **~4 GB of RAM free** for the GitLab container. GitLab CE is heavy.
- **git** and a **GitHub account**.
- Get the project: clone or download this repo, then `cd` into it. All paths
  below are relative to the repo root.

---

## Part 1 — Stand up a local GitLab CE + Runner ("step 0")

The goal of this part is to get GitLab running, register a runner, and confirm
the runner can pick up a job. No application code yet — just the platform.

### 1.1 Make the URL consistent (one-time)

GitLab and your browser must agree on a single URL. We use `http://gitlab:8929`
everywhere. Add a hosts entry so `gitlab` resolves to your machine:

```bash
echo "127.0.0.1 gitlab" | sudo tee -a /etc/hosts
```

(Inside Docker, the `gitlab` name already resolves via the compose network, so
now the host and the containers use the exact same URL. This avoids the most
common local-GitLab headache, where the runner cannot clone because the host
and containers disagree about the address.)

### 1.2 Start GitLab and the runner

```bash
docker compose -f local-gitlab/docker-compose.yml up -d
```

GitLab takes **3–5 minutes** to become healthy on first boot. Watch it:

```bash
docker compose -f local-gitlab/docker-compose.yml logs -f gitlab
```

Until it is ready, `http://gitlab:8929` may return 502. When it loads a login
page, you are good.

### 1.3 First login

GitLab generates a random root password on first boot:

```bash
docker exec gitlab cat /etc/gitlab/initial_root_password
```

Log in at `http://gitlab:8929` with username **`root`** and that password.
(The file is auto-deleted after 24 hours; change the password in the UI under
**User settings → Password** if you want a permanent one.)

### 1.4 Create a project

In the UI: **Create new... → New project/repository → Create blank project**.
Name it `numstats`, set visibility to Private (it is local anyway), and
**uncheck** "Initialize repository with a README" so it stays empty. Create it.

Note the project path — it will be something like `root/numstats`.

### 1.5 Create a runner and get its token

The modern GitLab flow creates the runner in the UI first, then gives you a
`glrt-` authentication token. (The old `--registration-token` method is
deprecated and may be disabled on GitLab 17.0+, returning `410 Gone`.)

1. Go to your project → **Settings → CI/CD → Runners** (expand the section).
2. Click **New project runner**.
3. Platform: **Linux**. Tick **"Run untagged jobs"** (so the runner accepts the
   jobs in this repo, which have no tags). Leave the rest default. **Create runner**.
4. GitLab shows a **runner authentication token** beginning with `glrt-`.
   Copy it now — it is shown only once.

### 1.6 Register the runner

Run this on your machine, pasting your `glrt-` token:

```bash
docker exec -it gitlab-runner gitlab-runner register \
  --non-interactive \
  --url "http://gitlab:8929" \
  --token "glrt-XXXXXXXXXXXXXXXXXXXX" \
  --executor "docker" \
  --docker-image "python:3.12-slim" \
  --docker-network-mode "gitlab-net" \
  --description "local-docker-runner"
```

Why these flags:

- `--url http://gitlab:8929` — the runner reaches GitLab over the compose network.
- `--executor docker` — every job runs in a fresh, isolated container.
- `--docker-image python:3.12-slim` — the default image jobs start from.
- `--docker-network-mode gitlab-net` — **important**: puts each job container on
  the same network, so it can resolve `gitlab` and clone the repo. Without this,
  jobs fail with `could not resolve host: gitlab`.

Confirm it registered:

```bash
docker exec gitlab-runner gitlab-runner list
```

Back in the UI (**Settings → CI/CD → Runners**) the runner should show a green
"online" dot within a few seconds.

### 1.7 (Optional) Sanity-check with a throwaway pipeline

To prove the runner picks up jobs before wiring in the real pipeline, you can
temporarily commit a one-job `.gitlab-ci.yml` like this:

```yaml
hello:
  image: alpine:latest
  script:
    - echo "Hello from a self-hosted GitLab pipeline!"
    - uname -a
```

Push it (see Part 2.3 for the git remote setup), watch it go green under
**Build → Pipelines**, then replace it with the real one. Or just skip ahead —
Part 2 uses the real pipeline directly.

---

## Part 2 — Run the Python pipeline ("option B")

The app is already in this repo. This part runs its real three-stage pipeline.

### 2.1 The project layout

```
.
├── .gitlab-ci.yml          # the pipeline: lint -> test -> build
├── pyproject.toml          # packaging, deps, ruff + pytest config
├── src/numstats/           # the package
│   ├── core.py             # pure functions (parse + summarize)  <- swap this later
│   └── cli.py              # argparse CLI wrapper
├── tests/                  # pytest unit tests
├── local-gitlab/           # the GitLab + runner compose from Part 1
└── .github/workflows/      # optional GitHub Actions mirror (Part 3)
```

The design point: **all the real logic is pure functions in `core.py`**, which
makes it trivial to test. When you grow the project, you replace `core.py` with
real domain logic and the pipeline stays the same shape.

### 2.2 Run it locally first

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest --cov=numstats
numstats 2 4 4 4 5 5 7 9
```

If that is green locally, it will be green in CI — the pipeline runs the same
commands.

### 2.3 Point this repo at your local GitLab and push

From the repo root, initialise git (if needed) and add your local GitLab as a
remote, then push:

```bash
git init -b main          # skip if already a git repo
git add -A
git commit -m "Initial commit: numstats CI starter"

git remote add gitlab http://gitlab:8929/root/numstats.git
git push -u gitlab main
```

When prompted for credentials, use username **`root`** and your GitLab password
(or a Project Access Token created under **Settings → Access Tokens**).

### 2.4 Watch the pipeline

In the GitLab UI: **Build → Pipelines**. You should see three stages run in
order: `lint`, `test`, `build`. Click into any job to see live logs.

When it finishes:

- The **test** job attaches a JUnit report (visible on the pipeline page) and
  the coverage % shows on the pipeline.
- The **build** job produces `dist/numstats-0.1.0-py3-none-any.whl` as a
  downloadable artifact (job page → **Download artifacts**).

Take a screenshot of the green pipeline — you will use it in the README.

---

## Part 3 — Publish to GitHub as portfolio

### 3.1 The mental model

The **pipeline runs on your self-hosted GitLab** — that is the skill on display,
and it is the thing recruiters/engineers cannot see by just browsing GitHub. So:

- **GitHub** holds the public code + the README with your pipeline screenshot.
- **GitLab (local)** is where the `.gitlab-ci.yml` actually executes.
- You keep both in sync with two git remotes.

### 3.2 Create the GitHub repo and add the remote

Create an empty public repo on GitHub named `gitlab-ci-python-starter` (no
README/license — this repo already has them). Then:

```bash
git remote add origin git@github.com:YOUR_USERNAME/gitlab-ci-python-starter.git
git push -u origin main
```

Now you have:

```
origin -> GitHub  (public portfolio)
gitlab -> local GitLab CE  (runs the real pipeline)
```

Day to day: `git push gitlab main` to run the pipeline, `git push origin main`
to publish. (You can also push to both: `git push origin main && git push gitlab main`.)

### 3.3 Add the screenshot

Drop your green-pipeline screenshot at `docs/img/pipeline-green.png`, then
uncomment the image line in `README.md`. A README that shows a passing
self-hosted pipeline is far more convincing than one that only describes it.

### 3.4 (Optional) Live green checks on GitHub

`.github/workflows/ci.yml` mirrors the lint+test steps on GitHub Actions, so the
GitHub page shows passing checks natively. This is a nice-to-have; the
`.gitlab-ci.yml` remains the real, self-hosted pipeline you are showcasing.

---

## Part 4 — Where to go next

Each of these is a small, self-contained upgrade that keeps the pipeline shape
and grows the project toward the larger aerospace telemetry platform:

1. **Add a `fetch` stage** as the first stage — download a public data file in
   the pipeline and pass it on as an artifact.
2. **Swap `core.py`** for real domain logic — e.g. validate a satellite TLE
   line's checksum and compute orbital parameters. The `test` stage gains a
   golden sanity check (the ISS period is ~92 minutes), exactly like the
   `stdev == 2.0` test already here.
3. **Add a `docker build`** stage that builds an image and pushes it to GitLab's
   built-in container registry.
4. **Add observability** — push pipeline metrics (duration, records processed,
   validation failures) to a Prometheus Pushgateway and chart them in Grafana.
5. **Provision with Terraform** — move GitLab onto a cloud host provisioned by
   Terraform instead of running locally.

---

## Troubleshooting

**`http://gitlab:8929` does not load in the browser** — the `/etc/hosts` entry
(Part 1.1) is missing. Add `127.0.0.1 gitlab`.

**GitLab returns 502 for a few minutes** — normal on first boot; it is still
initialising. Watch `docker compose -f local-gitlab/docker-compose.yml logs -f gitlab`.

**GitLab container restarts / runs out of memory** — GitLab CE needs ~4 GB.
Increase Docker's memory allocation, or stop other containers.

**Jobs stay "pending" forever** — the runner is not online, or you did not tick
**"Run untagged jobs"** when creating it. Check the runner's green dot under
Settings → CI/CD → Runners, and `docker exec gitlab-runner gitlab-runner list`.

**Job fails with `could not resolve host: gitlab`** — the job container is not
on the right network. Re-register the runner with
`--docker-network-mode gitlab-net`, and confirm the compose network is named
`gitlab-net` (it is, via the `name:` field in the compose file).

**`gitlab-runner register` returns `410 Gone`** — you used a legacy registration
token instead of a `glrt-` authentication token. Create the runner in the UI
first (Part 1.5) and use the `glrt-` token it gives you.

**`permission denied` on the Docker socket** — the runner container needs access
to `/var/run/docker.sock` (already mounted in the compose file). On a locked-down
host you may need to adjust socket permissions or the runner's group.

**Push to `gitlab` remote is rejected / asks endlessly for a password** — create
a Project Access Token (Settings → Access Tokens, `write_repository` scope) and
use it as the password with username `root`.

**Notes from a real Windows 10 setup**

These are extra notes from actually doing this on a Windows 10 laptop. They go
beyond the steps above, in case you hit the same problems.

**Docker Desktop says "Starting..." and never finishes.** This usually means
virtualization is turned off in the BIOS. Open PowerShell and run:

```powershell
Get-ComputerInfo -Property HyperVRequirementVirtualizationFirmwareEnabled
```

If this says `False`, restart the laptop, enter the BIOS (on a Lenovo ThinkPad,
tap F1 while booting), go to **Security → Virtualization**, and turn on
**Intel Virtualization Technology**. Save and exit. Docker Desktop should start
normally after the restart.

**The pipeline shows "Pending" or "stuck" forever, even though the runner has a
green dot.** The runner might not actually be reading its config file. Check
the runner's logs:

```powershell
docker logs gitlab-runner --tail 50
```

If you see repeated lines like `Failed to load config: no such file or
directory`, the runner's saved settings got lost or corrupted. The fix is to
wipe that runner's data and register it again from scratch:

```powershell
docker compose down
docker volume rm local-gitlab_gitlab-runner-config
docker compose up -d
```

Wait a few minutes for GitLab to fully start again, then create a brand new
runner in the GitLab UI and register it (see step 1.5 and 1.6 above). You will
get a new `glrt-` token each time you create a new runner — always use the
newest one.

**There are two kinds of runners in GitLab, and only one of them works for
this project.** A "project runner" only works for one project (this is what
you want). An "instance runner" is shared across the whole GitLab installation
and lives under the Admin Area, not under a project's own Settings. If you
only see an option to create an "instance runner", you are probably looking at
the Admin Area by mistake. Go to the project itself, then
**Settings → CI/CD → Runners**, and look for **"New project runner"** there
instead.

**After fixing the runner, an old pipeline still shows "Failed" or "stuck"
from before the fix.** That old pipeline ran under the broken runner setup and
will not fix itself. Ignore it and start a fresh one instead:
**Build → Pipelines → New pipeline → Run pipeline** on the `main` branch. The
new run will use the current, working runner.
