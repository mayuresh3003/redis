from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import redis
from kubernetes import client, config

app = FastAPI(
    title="Redis Ops API",
    description="Safely expose Redis + K8s operations for AI/automation",
    version="1.0.0",
)

# ---------- Config ----------
REDIS_MASTER_HOST = os.getenv("REDIS_MASTER_HOST", "redis-master.redis.svc.cluster.local")
REDIS_MASTER_PORT = int(os.getenv("REDIS_MASTER_PORT", "6381"))
REDIS_REPLICA_HOST = os.getenv("REDIS_REPLICA_HOST", "redis-replica.redis.svc.cluster.local")
REDIS_REPLICA_PORT = int(os.getenv("REDIS_REPLICA_PORT", "6382"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Kubernetes namespace for Redis resources
REDIS_NAMESPACE = os.getenv("REDIS_NAMESPACE", "redis")

# ---------- Redis clients ----------
r_master = redis.Redis(
    host=REDIS_MASTER_HOST,
    port=REDIS_MASTER_PORT,
    db=REDIS_DB,
    decode_responses=True,  # return strings instead of bytes
)
r_replica = redis.Redis(
    host=REDIS_REPLICA_HOST,
    port=REDIS_REPLICA_PORT,
    db=REDIS_DB,
    decode_responses=True,
)

# ---------- K8s client ----------
try:
    # running inside the cluster
    config.load_incluster_config()
except Exception:
    # fallback for local testing (use kubeconfig)
    config.load_kube_config()

core_v1 = client.CoreV1Api()


# ---------- Request models ----------
class SetKeyRequest(BaseModel):
    key: str
    value: str


class RestartPodRequest(BaseModel):
    pod_name: str


# ---------- Redis endpoints ----------
@app.get("/redis/get")
def redis_get(key: str):
    try:
        value = r_master.get(key)
        return {"key": key, "value": value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/redis/set")
def redis_set(body: SetKeyRequest):
    try:
        r_master.set(body.key, body.value)
        return {"status": "ok", "key": body.key, "value": body.value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/redis/flush")
def redis_flush():
    # WARNING: super destructive — in real life, add auth + confirmation
    try:
        r_master.flushall()
        return {"status": "flushed_all_databases"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/redis/replication-info")
def redis_replication_info():
    try:
        master_info = r_master.info("replication")
        replica_info = r_replica.info("replication")
        return {
            "master": master_info,
            "replica": replica_info,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- K8s endpoints ----------
@app.get("/k8s/pods")
def list_redis_pods():
    try:
        pods = core_v1.list_namespaced_pod(namespace=REDIS_NAMESPACE)
        result = []
        for p in pods.items:
            result.append({
                "name": p.metadata.name,
                "phase": p.status.phase,
                "host_ip": p.status.host_ip,
                "pod_ip": p.status.pod_ip,
                "containers": [c.name for c in p.spec.containers],
            })
        return {"pods": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/k8s/restart-pod")
def restart_pod(body: RestartPodRequest):
    try:
        core_v1.delete_namespaced_pod(
            name=body.pod_name,
            namespace=REDIS_NAMESPACE,
            body=client.V1DeleteOptions(),
        )
        return {"status": "restarted", "pod": body.pod_name}
    except client.exceptions.ApiException as e:
        raise HTTPException(status_code=e.status, detail=e.body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
