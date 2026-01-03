# Production Deployment Architecture

## Overview

Workflow Hub is designed as a **local-first** application. In production, it requires:
1. **Access to project codebases** - Agents need to read/write files, run tests, commit code
2. **Persistent storage** - Proofs, attachments, and work artifacts
3. **LLM access** - Docker Model Runner or external API

## Current Local Development Setup

```
┌─────────────────────────────────────────────────────────────┐
│                    Host Machine                              │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Django       │  │ Docker Model │  │ Project Repos│       │
│  │ Dev Server   │──│ Runner (DMR) │  │ /path/to/    │       │
│  │ :8000        │  │ :12434       │  │ projects/    │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│         │                                    │               │
│         └────────────────────────────────────┘               │
│                    │                                         │
│  ┌─────────────────▼─────────────────────────────────────┐  │
│  │              Docker Compose                            │  │
│  │  ┌──────────┐  ┌──────────┐                           │  │
│  │  │PostgreSQL│  │PostgREST │                           │  │
│  │  │ :5432    │  │ :3000    │                           │  │
│  │  └──────────┘  └──────────┘                           │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

- Django runs on host (not containerized) for filesystem access
- Agents (Goose) execute directly on host machine
- DMR runs on host for LLM inference
- Only DB and PostgREST are containerized

## Production Options

### Option 1: Single Server with Mounted Volumes (Simplest)

For a single-user or small team deployment:

```yaml
# docker-compose.prod.yml
services:
  app:
    build: .
    volumes:
      # Mount project workspace directory
      - /path/to/workspaces:/workspaces
      # Mount proofs directory for persistence
      - /path/to/proofs:/app/proofs
      # Optional: mount .ssh for git access
      - /home/user/.ssh:/home/appuser/.ssh:ro
    environment:
      WORKSPACE_ROOT: /workspaces
      PROOFS_ROOT: /app/proofs
      # DMR on host - use host.docker.internal on macOS/Windows
      # Use 172.17.0.1 on Linux
      LLM_BASE_URL: http://host.docker.internal:12434/engines/llama.cpp/v1
```

**Pros:**
- Simple setup
- Direct filesystem access
- Same model as local dev

**Cons:**
- Container can access host filesystem (security consideration)
- Single machine only

### Option 2: Network-Attached Storage (NAS)

For multi-server or team deployments:

```yaml
services:
  app:
    volumes:
      # NFS/SMB mounted workspace
      - type: nfs
        source: nas-server:/workspaces
        target: /workspaces
      # Or use named volume backed by NFS
      - workspaces:/workspaces

volumes:
  workspaces:
    driver: local
    driver_opts:
      type: nfs
      o: addr=nas.local,rw
      device: ":/workspaces"
```

### Option 3: Git-Based Workspace (Cloud-Native)

For cloud deployments without persistent filesystem:

```
┌─────────────────────────────────────────────────────────────┐
│                    Workflow Hub Container                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Django App   │  │ Agent Worker │  │ Ephemeral    │       │
│  │              │──│ (isolated)   │──│ Workspace    │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                                              │               │
│                                              │ git clone     │
│                                              │ on demand     │
│                                              ▼               │
│                                    ┌──────────────┐          │
│                                    │ Git Remote   │          │
│                                    │ (GitHub, etc)│          │
│                                    └──────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

**Workflow:**
1. Agent receives task
2. Clone repo to ephemeral workspace (container tmpfs or volume)
3. Execute agent work
4. Commit and push changes
5. Cleanup workspace

**Advantages:**
- Stateless containers
- Easy horizontal scaling
- No shared filesystem needed

**Implementation:**
```python
# agent_runner.py changes
def setup_workspace(project):
    workspace_dir = f"/tmp/workspaces/{project.id}"
    if project.repo_url:
        subprocess.run(["git", "clone", project.repo_url, workspace_dir])
    return workspace_dir

def cleanup_workspace(workspace_dir):
    shutil.rmtree(workspace_dir, ignore_errors=True)
```

### Option 4: Kubernetes with PersistentVolumes

For enterprise/cloud-native deployments:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: workspaces-pvc
spec:
  accessModes:
    - ReadWriteMany  # Shared across pods
  storageClassName: efs-sc  # EFS, NFS, etc.
  resources:
    requests:
      storage: 100Gi

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wfhub
spec:
  replicas: 1  # Only 1 for now (job coordination)
  template:
    spec:
      containers:
      - name: app
        volumeMounts:
        - name: workspaces
          mountPath: /workspaces
        - name: proofs
          mountPath: /app/proofs
      volumes:
      - name: workspaces
        persistentVolumeClaim:
          claimName: workspaces-pvc
```

## LLM Options for Production

### Option A: Docker Model Runner (Self-Hosted)

Run DMR on a GPU-equipped server:
```bash
# On GPU server
docker model serve --gpus all

# In app config
LLM_BASE_URL=http://gpu-server:12434/engines/llama.cpp/v1
```

### Option B: Ollama (Self-Hosted)

```bash
# On GPU server
ollama serve

# In app config
OLLAMA_HOST=http://gpu-server:11434
```

### Option C: Cloud API (OpenAI, Anthropic, etc.)

```python
# Future: Support multiple providers
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `WORKSPACE_ROOT` | Root directory for project workspaces | `/workspaces` |
| `PROOFS_ROOT` | Root directory for proof storage | `/app/proofs` |
| `LLM_BASE_URL` | LLM API endpoint | `http://localhost:12434/...` |
| `DATABASE_URL` | PostgreSQL connection | `postgresql://...` |

## Security Considerations

1. **Filesystem Access**
   - Limit volume mounts to specific directories
   - Use read-only where possible
   - Don't mount sensitive host directories

2. **Git Credentials**
   - Use deploy keys or access tokens
   - Store in environment, not filesystem
   - Consider GitHub App for repo access

3. **Agent Isolation**
   - Run agents in separate containers
   - Limit network access
   - Use resource limits (CPU, memory)

## Recommended Architecture for Production

For most deployments, we recommend **Option 1 (Single Server)** initially:

1. Run app on a dedicated server with:
   - NVMe storage for workspaces
   - Mounted `/workspaces` directory for projects
   - Docker for DB and supporting services
   - DMR or Ollama on the same machine (or separate GPU server)

2. Scale to **Option 4 (Kubernetes)** when you need:
   - Multiple team members
   - High availability
   - Cloud deployment

## Migration Path

1. **Dev → Single Server:** Direct copy of local setup
2. **Single Server → NAS:** Add network storage, update volume mounts
3. **NAS → Kubernetes:** Create PVCs, deploy with helm chart
