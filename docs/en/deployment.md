# AgentOS Deployment Guide

This guide covers deploying AgentOS in various environments.

---

## Local Development

```bash
git clone https://github.com/whiletrue247/AgentOS.git
cd AgentOS
pip install -e ".[all]"
python start.py
```

---

## Docker Compose (Recommended)

The included `docker-compose.yml` provides a complete stack:

```bash
# Start all services (AgentOS + PostgreSQL + Neo4j + Redis)
docker-compose up -d

# View logs
docker-compose logs -f agent_os

# Stop
docker-compose down
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI API key |
| `AGENTOS_PORT` | `8080` | Dashboard port |
| `AGENTOS_SOUL_PATH` | `./SOUL.md` | Path to SOUL.md |
| `AGENTOS_SANDBOX` | `docker` | Sandbox backend (docker/e2b) |

---

## Kubernetes

### Basic Deployment

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agentos
  labels:
    app: agentos
spec:
  replicas: 1
  selector:
    matchLabels:
      app: agentos
  template:
    metadata:
      labels:
        app: agentos
    spec:
      containers:
        - name: agentos
          image: ghcr.io/whiletrue247/agentos:latest
          ports:
            - containerPort: 8080
          env:
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: agentos-secrets
                  key: openai-api-key
          resources:
            requests:
              memory: "64Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "500m"
          volumeMounts:
            - name: data
              mountPath: /app/data
            - name: soul
              mountPath: /app/SOUL.md
              subPath: SOUL.md
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: agentos-data
        - name: soul
          configMap:
            name: agentos-soul

---
apiVersion: v1
kind: Service
metadata:
  name: agentos
spec:
  selector:
    app: agentos
  ports:
    - port: 80
      targetPort: 8080
  type: ClusterIP
```

### Create Secrets

```bash
kubectl create secret generic agentos-secrets \
  --from-literal=openai-api-key=sk-xxx

kubectl create configmap agentos-soul \
  --from-file=SOUL.md=./SOUL.md
```

### Apply

```bash
kubectl apply -f k8s/deployment.yaml
```

---

## AWS ECS (Fargate)

### Task Definition

```json
{
  "family": "agentos",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [
    {
      "name": "agentos",
      "image": "ghcr.io/whiletrue247/agentos:latest",
      "portMappings": [
        { "containerPort": 8080, "protocol": "tcp" }
      ],
      "environment": [
        { "name": "AGENTOS_PORT", "value": "8080" }
      ],
      "secrets": [
        {
          "name": "OPENAI_API_KEY",
          "valueFrom": "arn:aws:secretsmanager:region:account:secret:agentos/openai-key"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/agentos",
          "awslogs-region": "us-west-2",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

---

## Resource Requirements

| Environment | CPU | Memory | Storage |
|-------------|-----|--------|---------|
| **Minimal** | 1 vCPU | 128 MB | 500 MB |
| **Recommended** | 2 vCPU | 512 MB | 2 GB |
| **Production** (with KG) | 4 vCPU | 2 GB | 10 GB |

---

## Health Check

AgentOS exposes a health endpoint on the Dashboard:

```bash
curl http://localhost:8080/health
# Expected: {"status": "ok", "version": "5.1.0"}
```

---

## Multi-Node with Sync Handoff

For multi-node deployments, use `11_Sync_Handoff` to synchronize state:

```yaml
# In config.yaml
sync:
  enabled: true
  peers:
    - ws://node2:9090
    - ws://node3:9090
  checkpoint_interval: 300  # seconds
```

Each node maintains its own state and synchronizes via WebSocket.
