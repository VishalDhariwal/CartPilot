#!/usr/bin/env bash
# ==============================================================================
# CartPilot Azure Infrastructure & GitHub Actions CI/CD Provisioning Script
# ==============================================================================
set -e

RESOURCE_GROUP="${RESOURCE_GROUP:-cartpilot-rg}"
LOCATION="${LOCATION:-centralindia}"
CONTAINER_APP_ENV="${CONTAINER_APP_ENV:-cartpilot-env}"
CONTAINER_APP_NAME="${CONTAINER_APP_NAME:-cartpilot-app}"

echo "========================================================================"
echo "🚀 CartPilot Azure Infrastructure & CI/CD Setup"
echo "========================================================================"

# 1. Verify Azure CLI Authentication
if ! az account show >/dev/null 2>&1; then
  echo "❌ Error: Azure CLI is not logged in. Please run 'az login' first."
  exit 1
fi

SUBSCRIPTION_ID=$(az account show --query id -o tsv)
SUBSCRIPTION_NAME=$(az account show --query name -o tsv)
echo "✅ Logged in to Azure Subscription: $SUBSCRIPTION_NAME ($SUBSCRIPTION_ID)"

# 2. Add / Upgrade ContainerApp Azure CLI extension
echo "📦 Ensuring 'containerapp' Azure CLI extension is installed..."
az extension add --name containerapp --upgrade --yes >/dev/null 2>&1 || true

# 3. Create or Verify Resource Group
if ! az group show --name "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "📁 Creating Resource Group '$RESOURCE_GROUP' in '$LOCATION'..."
  az group create --name "$RESOURCE_GROUP" --location "$LOCATION" -o none
else
  echo "📁 Resource Group '$RESOURCE_GROUP' already exists."
fi

# 4. Check or Create Azure Container Registry (ACR)
EXISTING_ACR=$(az acr list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv 2>/dev/null || true)
if [ -z "$EXISTING_ACR" ] || [ "$EXISTING_ACR" = "None" ]; then
  # Generate unique name
  RANDOM_HEX=$(openssl rand -hex 3 2>/dev/null || echo "$RANDOM")
  ACR_NAME="cartpilotacr${RANDOM_HEX}"
  echo "📦 Creating Azure Container Registry '$ACR_NAME'..."
  az acr create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ACR_NAME" \
    --sku Basic \
    --admin-enabled true \
    -o none
else
  ACR_NAME="$EXISTING_ACR"
  echo "📦 Using existing ACR '$ACR_NAME'..."
fi

ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
ACR_CREDS=$(az acr credential show --name "$ACR_NAME" -o json)
ACR_USERNAME=$(echo "$ACR_CREDS" | grep -o '"username": *"[^"]*"' | head -1 | cut -d'"' -f4)
ACR_PASSWORD=$(echo "$ACR_CREDS" | grep -o '"value": *"[^"]*"' | head -1 | cut -d'"' -f4)
echo "✅ ACR Ready: $ACR_LOGIN_SERVER"

# 5. Create or Verify Container Apps Environment
if ! az containerapp env show --name "$CONTAINER_APP_ENV" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "🌐 Creating Container Apps Environment '$CONTAINER_APP_ENV'..."
  az containerapp env create \
    --name "$CONTAINER_APP_ENV" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    -o none
else
  echo "🌐 Container Apps Environment '$CONTAINER_APP_ENV' already exists."
fi

# 6. Create or Verify Azure Container App
if ! az containerapp show --name "$CONTAINER_APP_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  echo "🚀 Creating Container App '$CONTAINER_APP_NAME' (Port 8000, External Ingress)..."
  az containerapp create \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$CONTAINER_APP_ENV" \
    --image "mcr.microsoft.com/k8se/quickstart:latest" \
    --target-port 8000 \
    --ingress external \
    --cpu 0.75 \
    --memory 1.5Gi \
    --registry-server "$ACR_LOGIN_SERVER" \
    --registry-username "$ACR_USERNAME" \
    --registry-password "$ACR_PASSWORD" \
    --env-vars \
      BYPASS_RAZORPAY="true" \
      DEFAULT_WEATHER_CITY="Delhi" \
    -o none
else
  echo "🚀 Container App '$CONTAINER_APP_NAME' already exists."
fi

APP_FQDN=$(az containerapp show --name "$CONTAINER_APP_NAME" --resource-group "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "")

# 7. Create Service Principal for GitHub Actions
echo "🔑 Generating Azure Service Principal for GitHub Actions..."
SP_JSON=$(az ad sp create-for-rbac \
  --name "cartpilot-github-actions-${RANDOM}" \
  --role "Contributor" \
  --scopes "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" \
  --sdk-auth 2>/dev/null || echo "")

# 8. Set GitHub Secrets via GitHub CLI (if authenticated)
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo "🐙 GitHub CLI is authenticated! Configuring repository secrets..."
  gh secret set ACR_LOGIN_SERVER -b "$ACR_LOGIN_SERVER"
  gh secret set ACR_USERNAME -b "$ACR_USERNAME"
  gh secret set ACR_PASSWORD -b "$ACR_PASSWORD"
  gh secret set CONTAINER_APP_NAME -b "$CONTAINER_APP_NAME"
  gh secret set RESOURCE_GROUP -b "$RESOURCE_GROUP"

  if [ -n "$SP_JSON" ]; then
    gh secret set AZURE_CREDENTIALS -b "$SP_JSON"
    echo "✅ Secret AZURE_CREDENTIALS configured."
  fi
  echo "✅ GitHub Secrets successfully set in repository!"
else
  echo "ℹ️ GitHub CLI (gh) not authenticated. Manual secret copy required."
fi

echo ""
echo "========================================================================"
echo "🎉 Azure Infrastructure Provisioning Complete!"
echo "========================================================================"
if [ -n "$APP_FQDN" ]; then
  echo "🌍 Public Application URL: https://$APP_FQDN"
fi
echo ""
echo "📋 GitHub Repository Secrets Checklist:"
echo "------------------------------------------------------------------------"
echo "ACR_LOGIN_SERVER   : $ACR_LOGIN_SERVER"
echo "ACR_USERNAME       : $ACR_USERNAME"
echo "CONTAINER_APP_NAME : $CONTAINER_APP_NAME"
echo "RESOURCE_GROUP     : $RESOURCE_GROUP"
echo ""
if [ -n "$SP_JSON" ]; then
  echo "AZURE_CREDENTIALS (Paste into GitHub Secrets if not auto-set):"
  echo "$SP_JSON"
fi
echo "========================================================================"
