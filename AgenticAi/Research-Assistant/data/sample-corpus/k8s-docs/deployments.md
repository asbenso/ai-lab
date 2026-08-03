<!-- source: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/ -->

# Deployments

A Deployment provides declarative updates for Pods and ReplicaSets. You describe a desired state in a Deployment, and the Deployment Controller changes the actual state to the desired state at a controlled rate.

## Rolling updates

The default strategy is RollingUpdate, which incrementally replaces Pods with new versions while keeping the application available. Tune `maxSurge` and `maxUnavailable` to control the rollout speed and capacity headroom.

## Rollback

`kubectl rollout undo deployment/<name>` reverts to the previous ReplicaSet. Use `kubectl rollout history` to inspect prior revisions, and `--revision=<n>` to roll back to a specific version.

## Probes

Always configure `readinessProbe` so traffic is only sent to ready Pods, and `livenessProbe` so the kubelet can restart stuck containers. Without a readinessProbe, a rolling update can briefly send traffic to a starting Pod.
