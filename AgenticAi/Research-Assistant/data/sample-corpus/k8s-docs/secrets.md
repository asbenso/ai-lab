<!-- source: https://kubernetes.io/docs/concepts/configuration/secret/ -->

# Secrets

A Secret is an object that contains a small amount of sensitive data such as a password, a token, or a key. Such information might otherwise be put in a Pod specification or in a container image.

## Encryption at rest

By default, Secret data is stored unencrypted in etcd. Enable EncryptionConfiguration to encrypt Secrets at rest with an envelope encryption provider (KMS or AES-CBC). Without it, anyone with read access to etcd can read every Secret.

## RBAC

Use Role-Based Access Control to limit which Service Accounts can read which Secrets. Avoid wildcards in production. Audit `kubectl get secrets` access via the API audit log.

## Better alternatives

For cloud workloads prefer External Secrets Operator with AWS Secrets Manager or GCP Secret Manager - the cluster never stores the secret material; the operator syncs values into Pods at runtime.
