<!-- source: https://docs.aws.amazon.com/AmazonS3/latest/userguide/serv-side-encryption.html -->

# Server-side encryption for Amazon S3

Amazon S3 applies server-side encryption with Amazon S3 managed keys (SSE-S3) as the base level of encryption for all object uploads at no cost. You can choose to use server-side encryption with AWS KMS keys (SSE-KMS) for additional control and auditing.

## Default encryption

Every new object uploaded to an S3 bucket is encrypted at rest using SSE-S3 (AES-256) unless you specify another method. The encryption header can be set per-object via `x-amz-server-side-encryption`.

## Bucket Keys

For SSE-KMS, S3 Bucket Keys reduce KMS request costs by up to 99% by using a short-lived bucket-level key. Enable Bucket Keys on the bucket; existing objects retain their original encryption.

## Best practices

- Block public access at the account level.
- Use SSE-KMS with customer-managed keys for regulated data; rotate the key on a defined schedule.
- Turn on S3 access logs and forward to CloudWatch for audit.
