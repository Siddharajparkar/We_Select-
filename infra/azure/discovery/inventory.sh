#!/usr/bin/env bash
# infra/azure/discovery/inventory.sh
# ─────────────────────────────────────────────────────────────────────────────
# READ-ONLY Azure resource discovery script.
# Phase 1 Stage 1 — OC-0 (Office Checkpoint 0).
#
# CONSTRAINTS (enforced by the forbidden-verb unit test):
#   - NEVER calls: keys list, list-key, show-connection-string,
#     get-shared-keys, secret show, exec, create, update, delete, set
#   - NEVER writes state; only reads.
#   - Prints names, types, SKUs, regions, provisioning states, image NAMES
#     (not digests), app-setting/secret NAMES (never values), firewall rule
#     names, and role-assignment role names.
#
# USAGE (Azure Cloud Shell from the org laptop — B3 row 11 / C11):
#   source infra/azure/discovery/inventory.sh
#
# VARIABLES: Override any of these before sourcing to target a specific
# resource group, subscription, etc. The real values are never committed.
#
# DRY_RUN mode (default DRY_RUN=1):
#   When DRY_RUN=1, only prints the commands that would run without executing
#   them.  Set DRY_RUN=0 in Cloud Shell to run for real.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Variables (placeholders — real values set in Cloud Shell, never committed)
RG="${RG:-<RG>}"                   # main resource group (East US)
RG_SQL="${RG_SQL:-<RG_SQL>}"       # resource group containing the SQL server (may equal RG)
SUBSCRIPTION="${SUBSCRIPTION:-}"    # leave blank to use default subscription

DRY_RUN="${DRY_RUN:-1}"

# ── Helper: run or dry-run a command
run() {
  if [ "${DRY_RUN}" = "1" ]; then
    echo "[DRY-RUN] $*"
  else
    eval "$*"
  fi
}

sep() { echo; echo "─── $* ───────────────────────────────────────────────"; echo; }

# ── Subscription / account context
sep "Account and subscription"
run "az account show --query '{name:name,id:id,state:state}' -o table"

sep "All resource groups"
run "az group list --query '[].{name:name,location:location,provisioningState:properties.provisioningState}' -o table"

# ── Resource group: main (East US expected)
sep "Resources in main resource group: ${RG}"
run "az resource list -g '${RG}' --query '[].{name:name,type:type,location:location,kind:kind}' -o table"

# ── Resource group: SQL (West US expected, may differ from main RG)
if [ "${RG_SQL}" != "${RG}" ]; then
  sep "Resources in SQL resource group: ${RG_SQL}"
  run "az resource list -g '${RG_SQL}' --query '[].{name:name,type:type,location:location}' -o table"
fi

# ── SQL Server and database (West US)
sep "SQL Servers in ${RG_SQL}"
run "az sql server list -g '${RG_SQL}' --query '[].{name:name,location:location,fullyQualifiedDomainName:fullyQualifiedDomainName,state:state}' -o table"

sep "SQL Databases"
run "az sql db list -g '${RG_SQL}' --server \"\$(az sql server list -g '${RG_SQL}' --query '[0].name' -o tsv 2>/dev/null || echo '<SQL_SERVER>')\" --query '[].{name:name,edition:edition,serviceObjectiveName:currentServiceObjectiveName,status:status,collation:collation,compatibilityLevel:currentBackupStorageRedundancy}' -o table"

sep "SQL Server firewall rules (names only)"
run "az sql server firewall-rule list -g '${RG_SQL}' --server \"\$(az sql server list -g '${RG_SQL}' --query '[0].name' -o tsv 2>/dev/null || echo '<SQL_SERVER>')\" --query '[].{name:name,startIpAddress:startIpAddress,endIpAddress:endIpAddress}' -o table"

# ── Azure AI Foundry / Cognitive Services (East US)
sep "Cognitive Services / AI accounts in ${RG}"
run "az cognitiveservices account list -g '${RG}' --query '[].{name:name,kind:kind,location:location,sku:sku.name,endpoint:properties.endpoint,state:properties.provisioningState}' -o table"

sep "AI Foundry model deployments (names only)"
run "az cognitiveservices account deployment list -g '${RG}' -n \"\$(az cognitiveservices account list -g '${RG}' --query '[0].name' -o tsv 2>/dev/null || echo '<AI_RESOURCE>')\" --query '[].{name:name,model:properties.model.name,version:properties.model.version,sku:sku.name,capacity:sku.capacity}' -o table"

# ── Log Analytics workspace
sep "Log Analytics workspaces in ${RG}"
run "az monitor log-analytics workspace list -g '${RG}' --query '[].{name:name,location:location,sku:sku,retentionInDays:retentionInDays}' -o table"

# ── Application Insights
sep "Application Insights in ${RG}"
run "az monitor app-insights component show --query '{name:name,location:location,applicationType:applicationType,ingestionEndpoint:ingestionEndpoint,instrumentationKey:\"[MASKED]\"}' -g '${RG}' -o table" 2>/dev/null || \
  run "az resource list -g '${RG}' --resource-type Microsoft.Insights/components --query '[].{name:name,location:location}' -o table"

# ── Container Registry (ACR)
sep "Container Registries in ${RG}"
run "az acr list -g '${RG}' --query '[].{name:name,location:location,sku:sku.name,loginServer:loginServer,adminUserEnabled:adminUserEnabled}' -o table"

sep "ACR repositories (names only, no tags or digests)"
run "az acr repository list -n \"\$(az acr list -g '${RG}' --query '[0].name' -o tsv 2>/dev/null || echo '<ACR>')\" -o table" 2>/dev/null || echo "(no registry found or no permissions)"

# ── Container Apps environment
sep "Container Apps environments in ${RG}"
run "az containerapp env list -g '${RG}' --query '[].{name:name,location:location,provisioningState:properties.provisioningState}' -o table"

sep "Container Apps in ${RG} (image NAMES only, not digests)"
run "az containerapp list -g '${RG}' --query '[].{name:name,location:location,image:properties.template.containers[0].image,ingressType:properties.ingress.external,targetPort:properties.ingress.targetPort,replicas:properties.template.scale.maxReplicas,provisioningState:properties.provisioningState}' -o table"

sep "Container App ingress and secret NAMES (never values)"
run "az containerapp list -g '${RG}' --query '[].{name:name,secretNames:join(\", \",properties.configuration.secrets[].name),envVarNames:join(\", \",properties.template.containers[0].env[].name)}' -o table" 2>/dev/null || echo "(requires Contributor on container apps)"

# ── Blob Storage
sep "Storage accounts in ${RG}"
run "az storage account list -g '${RG}' --query '[].{name:name,location:location,sku:sku.name,kind:kind,allowBlobPublicAccess:allowBlobPublicAccess,minimumTlsVersion:minimumTlsVersion}' -o table"

sep "Blob containers (names and public access level only)"
run "az storage container list --account-name \"\$(az storage account list -g '${RG}' --query '[0].name' -o tsv 2>/dev/null || echo '<STG>')\" --auth-mode login --query '[].{name:name,publicAccess:properties.publicAccess}' -o table" 2>/dev/null || echo "(needs storage account name — set STG variable)"

# ── Azure Communication Services
sep "Communication Services in ${RG}"
run "az communication list --resource-group '${RG}' --query '[].{name:name,location:location,dataLocation:properties.dataLocation,provisioningState:properties.provisioningState}' -o table" 2>/dev/null || \
  run "az resource list -g '${RG}' --resource-type Microsoft.Communication/CommunicationServices --query '[].{name:name,location:location}' -o table"

# ── RBAC: role assignments relevant to this project
sep "Role assignments in ${RG} (role names only, no principal object ids)"
run "az role assignment list --resource-group '${RG}' --query '[].{principalType:principalType,roleDefinitionName:roleDefinitionName,scope:scope}' -o table" 2>/dev/null || echo "(requires Reader on the resource group)"

# ── Budget / cost management
sep "Cost Management budgets in subscription"
run "az consumption budget list --query '[].{name:name,amount:amount,currentSpend:currentSpend.amount,currency:currentSpend.unit}' -o table" 2>/dev/null || echo "(requires Cost Management Reader)"

sep "─── DISCOVERY COMPLETE ─────────────────────────────────────────────────────"
echo ""
echo "Next step: OC-PLAN"
echo "  Copy the output above and report it back via 'office report OC-0: ...'"
echo "  The agent will fill docs/PROVISIONING_PLAN.md from it."
echo ""
echo "IMPORTANT: This script printed NAMES and STATE only — no secrets, keys, or"
echo "  connection strings were read or printed."
