<!-- source: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys_manage.html -->

# Managing access keys for IAM users

To rotate access keys for an IAM user without interrupting your applications, complete the following steps. Create a second access key while the first is still active, update your applications to use the new key, and then disable (do not delete) the first key. Monitor your applications and your CloudTrail logs to confirm that nothing is still using the old key. Once you are certain, delete the old key.

## Best practices

Rotate access keys regularly. Most security frameworks recommend at most 90 days between rotations. Use AWS IAM Identity Center for human users instead of long-lived access keys whenever possible.

## Step-by-step

1. In the IAM console, choose Users, then choose the user whose key you want to rotate.
2. On the Security credentials tab, choose Create access key. Save the new key in a secure location.
3. Update your application configuration with the new key.
4. Return to IAM and set the old key's status to Inactive.
5. Verify your application continues to work.
6. Delete the old key.
