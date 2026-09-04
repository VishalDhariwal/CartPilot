# Azure CI/CD & Production Deployment Guide for CartPilot

This guide explains how to set up automated CI/CD for CartPilot using your own Azure account and personal Azure Container Registry (ACR).

---

## 1. Overview of Workflows

CartPilot includes three independent GitHub Actions workflows located in `.github/workflows/`:

| Workflow File | Trigger | Responsibility |
| :--- | :--- | :--- |
| **`ci.yml`** | Pull Requests, Pushes | Runs Python 3.11 unit tests (`pytest`) and verifies React frontend build (`npm run build`). |
| **`release-tag-on-merge.yml`** | Push to `main`, Manual Dispatch | Automatically computes the next version tag (e.g. `v1.0.0`), tags the commit, and publishes an official GitHub Release with release notes. |
| **`azure-container-publish.yml`** | Push to `main`, Tags `v*`, Manual Dispatch | Builds the optimized multi-stage Docker container (`Dockerfile`) using Docker Buildx and pushes to your private Azure Container Registry with commit SHA, semver, and `latest` tags. |

---

## 2. Setting Up Azure Container Registry (ACR)

You can configure Azure Container Registry using the **Azure CLI** or the **Azure Portal**.

### Option A: Using Azure CLI

1. **Log in to your Azure account:**
   ```bash
   az login
   ```

2. **Create a Resource Group (if you haven't already):**
   ```bash
   az group create --name CartPilot-RG --location eastus
   ```

3. **Create an Azure Container Registry:**
   > **Note:** ACR names must be globally unique, alphanumeric only, between 5-50 characters.
   ```bash
   az acr create \
     --resource-group CartPilot-RG \
     --name cartpilotregistry \
     --sku Basic \
     --admin-enabled true
   ```

4. **Retrieve Registry Login Credentials:**
   ```bash
   az acr credential show --name cartpilotregistry
   ```
   This will output:
   ```json
   {
     "username": "cartpilotregistry",
     "passwords": [
       { "name": "password", "value": "AbCdEf12345..." },
       { "name": "password2", "value": "XyZ987654..." }
     ]
   }
   ```
   - Your login server will be: `cartpilotregistry.azurecr.io`

---

## 3. Configuring Secrets in Your GitHub Repository

1. Open your CartPilot repository on GitHub.
2. Go to **Settings** > **Secrets and variables** > **Actions**.
3. Under **Repository secrets**, click **New repository secret** and add:

| Secret Name | Description / Example |
| :--- | :--- |
| **`ACR_LOGIN_SERVER`** | Your registry domain, e.g. `cartpilotregistry.azurecr.io` |
| **`ACR_USERNAME`** | Username from `az acr credential show`, e.g. `cartpilotregistry` |
| **`ACR_PASSWORD`** | Password from `az acr credential show` |

> [!TIP]
> **Alternative: Azure Service Principal**
> If your organization requires Service Principals instead of admin credentials, create one with:
> ```bash
> az ad sp create-for-rbac \
>   --name "cartpilot-gh-actions" \
>   --role "AcrPush" \
>   --scopes /subscriptions/<SUBSCRIPTION_ID>/resourceGroups/CartPilot-RG/providers/Microsoft.ContainerRegistry/registries/cartpilotregistry \
>   --sdk-auth
> ```
> Paste the resulting JSON into a single secret named **`AZURE_CREDENTIALS`**. The workflow automatically detects and uses it.

---

## 4. Running the Workflow Manually (On-Demand)

You do not need to push to `main` to test the container build:

1. On GitHub, go to the **Actions** tab.
2. Select **"Build and Publish Azure Container Image"**.
3. Click **Run workflow**:
   - Choose your active branch (e.g. `vishal-fixes` or `main`).
   - Image Name: `cartpilot-app`
   - Push Latest: `true`
4. Watch the build execute and confirm that the image appears in your Azure Container Registry.

You can inspect the published repository in Azure:
```bash
az acr repository list --name cartpilotregistry --output table
az acr repository show-tags --name cartpilotregistry --repository cartpilot-app --output table
```

---

## 5. Deploying CartPilot to Azure Container Apps

Once your image is published in ACR, you can run CartPilot on Azure Container Apps with high scalability and automatic HTTPS.

### Step 1: Create Container App Environment
```bash
az containerapp env create \
  --name cartpilot-env \
  --resource-group CartPilot-RG \
  --location eastus
```

### Step 2: Deploy CartPilot Container App
```bash
az containerapp create \
  --name cartpilot-app \
  --resource-group CartPilot-RG \
  --environment cartpilot-env \
  --image cartpilotregistry.azurecr.io/cartpilot-app:latest \
  --registry-server cartpilotregistry.azurecr.io \
  --registry-username cartpilotregistry \
  --registry-password "<YOUR_ACR_PASSWORD>" \
  --target-port 8000 \
  --ingress external \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars \
    DATABASE_URL="postgresql://<user>:<password>@<your-postgres-host>.postgres.database.azure.com:5432/cartpilot?sslmode=require" \
    GEMINI_API_KEY="<your-gemini-key>" \
    RAZORPAY_KEY_ID="<your-razorpay-key-id>" \
    RAZORPAY_KEY_SECRET="<your-razorpay-key-secret>" \
    MERCHANT_HMAC_SECRET="<your-secure-hmac-secret>"
```

Once provisioned, Azure will provide the public Application URL (e.g. `https://cartpilot-app.<env-id>.eastus.azurecontainerapps.io`).
Opening this URL loads the unified CartPilot Merchant Control Room, Catalog Diagnostics, and Buyer Commerce App.
