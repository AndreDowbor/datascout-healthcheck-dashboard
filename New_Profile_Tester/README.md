# 🦊 Datascout Clients - One Password Access 
---

### 1Password Python SDK
https://1password.com

### Documentation
https://developer.1password.com/docs/sdks/

### Examples
https://github.com/1Password/onepassword-sdk-python/tree/main/example

---

## Requirements

The 1Password Python SDK is compatible with:

- `python` 3.9 or later
- `libssl` 3
- `glibc` 2.32 or later

If you're running a Linux distribution that still uses `libssl` version 1.1.1, such as Debian 11 or Ubuntu 20.04, you'll need to update to a later version of Linux or install the required dependencies.

## 🚀 Get started

To use the 1Password Python SDK in your project:

1.  Find the credentials for the `Datascout 1Password Service Account` inside the DataScout.ai 1Password vault.

2. Provision your service account token and vault ID in a `.env` file at the root directory of the repository.

   **macOS or Linux**

   ```bash
   export OP_SERVICE_ACCOUNT_TOKEN=<datascout-service-account-token>
   export OP_VAULT_ID=<datascout-client-vault-id>
   ```

   **Windows**

   ```powershell
   $Env:OP_SERVICE_ACCOUNT_TOKEN = "<datascout-service-account-token>"
   $Env:OP_VAULT_ID = "<datascout-client-vault-id>"
   ```

3. Install the 1Password Python SDK in your project:

   ```bash
   pip install onepassword-sdk
   ```