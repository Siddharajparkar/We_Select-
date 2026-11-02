# Architectural Evaluation & Phase 1 Pre-Provisioning Plan

**Project:** AI Candidate Assessment Platform (MVP Backend)  
**Document Status:** PENDING USER REVIEW & CLOUD SHELL VERIFICATION  
**Author:** Antigravity Engineering  
**Date:** 2026-11-01  

---

## 1. Executive Summary & Existing Architecture

The Assessment Portal project is an active, existing platform deployed across two Azure regions:
- **East US:** Hosts the Assessment Portal application resources, centralized logs (Log Analytics & Application Insights), and the Azure AI Foundry resource (`<AI_RESOURCE>`).
- **West US:** Hosts the Assessment SQL Server and SQL Database, deployed there due to regional Azure SQL service tier and deployment availability constraints.

This document provides:
1. Regional mapping of existing vs. new resources.
2. Latency, networking, and security evaluation for cross-region communication.
3. SQL Database reuse recommendation and safeguards.
4. Estimated monthly cost breakdown fitting within the **$25.00 USD ceiling**.
5. Safe, non-intrusive **Cloud Shell commands** and **Azure Portal inspection steps** to run from your organization-provided laptop.
6. A resource-by-resource Phase 1 execution plan.

> [!IMPORTANT]
> **No Azure resources will be created, modified, migrated, or deleted** until you have inspected your environment and explicitly approved this plan.

---

## 2. Regional Resource Mapping

| Resource Category | Existing / New | Recommended Region | Resource Name / Identifier | Purpose |
|---|---|---|---|---|
| **SQL Server** | Existing | **West US** | `[PENDING VERIFICATION]` | Hosts the SQL Database. Preserved in West US. |
| **SQL Database** | Existing | **West US** | `[PENDING VERIFICATION]` | Shared relational store (tenants, users, assessments, jobs). |
| **AI Foundry (GPT-4o)** | Existing | **East US** | `<AI_RESOURCE>` | Question generation & descriptive answer evaluation. |
| **Log Analytics & App Insights** | Existing | **East US** | `[PENDING VERIFICATION]` | Centralized telemetry, performance monitoring, audit log mirror. |
| **Container Registry (ACR)** | New or Reuse | **East US** | `myassessacr` (or reuse existing) | Docker image storage for `assess-api`. |
| **Container Apps Environment** | New or Reuse | **East US** | `assess-env` (or reuse existing) | Managed serverless container host. |
| **API Container App (`assess-api`)**| New | **East US** | `assess-api` | Express / TypeScript backend, job engine, external ingress. |
| **Blob Storage (`jd-files`)** | New or Reuse | **East US** | `[PENDING VERIFICATION]` | Uploaded Job Description PDF/TXT files (private container). |
| **Email Service (ACS)** | New or Reuse | **East US / US** | `[PENDING VERIFICATION]` | Azure Communication Services with Azure-managed domain. |

---

## 3. Deployment Region for `assess-api`: East US vs. West US

### Recommendation: **Deploy `assess-api` in East US**

#### Architectural Justification:
1. **Frontend Colocation:** The user-facing Assessment Portal (`web` / frontend) is located in East US. Placing `assess-api` in East US ensures low intra-region latency (< 5 ms) for candidate exam sessions, autosaves, and cookie security (`sid`, `aid`).
2. **AI Payload Bandwidth:** GPT-4o requests and responses pass between the API and `<AI_RESOURCE>` (East US). Keeping them intra-region reduces transfer time and eliminates cross-region data transfer charges on AI payloads.
3. **Telemetry Colocation:** Application Insights and Log Analytics are in East US. Ingesting traces, metrics, and HTTP request logs stays within the same region (zero egress cost).
4. **Database Query Latency Handling:**
   - Round-trip ping between East US and West US over Microsoft's private backbone is ~65 ms to 75 ms.
   - Using persistent TCP/TLS connection pooling in Node.js (`mssql` pool) avoids the 3-way handshake + TLS negotiation on every request.
   - Fast transactional queries (e.g., candidate autosave: `UPDATE responses...`) execute in ~70 ms total, well under the 1,000 ms SLA.
   - Long-running tasks (AI question generation, descriptive marking, email dispatch) run asynchronously in the background job loop (`jobs` table) and never block HTTP client requests.

---

## 4. Existing SQL Database Reuse Recommendation

### Recommendation: **Reuse the existing West US SQL Database**

#### Benefits:
- **Zero Additional Cost:** No duplicate database billing (avoids an extra $5–$15/month).
- **Consolidated Data Model:** Candidate records, assessments, and audit trails remain in a single authoritative data store.
- **Respects Availability Constraints:** Leverages the region where your subscription has verified SQL capacity.

#### Pre-Provisioning Safety Invariants:
1. **Schema Check:** Inspect existing tables in Cloud Shell before applying Phase 2 migrations to ensure no naming collisions.
2. **Idempotency:** All migrations use `IF OBJECT_ID(...) IS NULL` and `schema_migrations` tracking.
3. **Least-Privilege App User:** Do not use `sqladmin`. Provision a dedicated `assess_app` user with `db_datareader`, `db_datawriter`, and `db_ddladmin` roles.
4. **Firewall Rule:** Add the `AllowAzureServices` firewall rule (`0.0.0.0` - `0.0.0.0`) on the West US SQL Server so East US Container Apps can connect securely via TLS 1.2.

---

## 5. Cross-Region Networking, Latency & Cost Evaluation

| Factor | Technical Assessment | Mitigation / Result |
|---|---|---|
| **Latency** | ~65–75 ms round-trip between East US (API) and West US (SQL). | Connection pooling (`max: 10`, persistent); single-round-trip queries; asynchronous background job loop. |
| **Security & TLS** | SQL traffic traverses Microsoft's encrypted backbone. | `Encrypt=true; TrustServerCertificate=false; MinimalTlsVersion=1.2`. |
| **Firewall** | Access control on West US SQL Server. | `AllowAzureServices` rule enables Container Apps without opening public internet access. |
| **Data Transfer Cost** | $0.02 per GB cross-region outbound. | Assessment responses are ~1 KB each. 50,000 saves = 50 MB = **$0.001** (negligible). |

---

## 6. Monthly Cost Estimate vs. $25.00 USD Budget Ceiling

| Service | SKU / Sizing | Estimated Monthly Cost | Budget Impact |
|---|---|---|---|
| **Azure SQL Database** | Existing (West US) | **$0.00** (already active) | Reused — zero incremental cost |
| **Azure Container Apps** | 1 replica (0.25–0.5 vCPU, 0.5–1 GiB) | **~$6.00 – $9.00** | First 180,000 vCPU-s & 360,000 GiB-s are **FREE** |
| **Container Registry (ACR)** | Basic SKU | **~$5.00** ($0.167/day) | Required for Docker images (or reuse existing) |
| **Azure Storage (Blob)** | Standard LRS Hot (`jd-files`) | **< $0.50** | Pennies for low-volume PDF storage |
| **Log Analytics & Insights** | Pay-as-you-go | **< $1.00** | First 5 GB ingestion/month is **FREE** |
| **Azure AI Foundry (GPT-4o)** | Pay-per-token (Global Standard) | **~$2.00 – $4.00** | ~20 test calls/day (~500k tokens/mo) |
| **Communication Services** | Azure-managed domain | **< $0.50** | $0.00025 per email (200 test invites = $0.05) |
| **Cross-Region Egress** | East US ↔ West US | **< $0.10** | Database query payload transfer |
| **Total Estimated Incremental Cost** | | **~$14.00 – $20.00 / month** | **FITS WITHIN $25.00 CEILING** |

### Budget Rails:
- Configure Azure Budget Alert at:
  - 50% ($12.50) — Notification warning.
  - 80% ($20.00) — Investigation threshold.
  - 100% ($25.00) — Ceiling limit.

---

## 7. Cloud Shell Inspection Commands (For Organization Laptop)

Please run the following commands in **Azure Cloud Shell** (Bash) on your organization-provided laptop and share the non-sensitive output.

> [!NOTE]
> None of these commands output passwords, access keys, or secrets.

### Step 1: Verify Subscription & Resource Groups
```bash
# Verify active subscription
az account show --query "{subscriptionId:id, name:name, tenantId:tenantId}" -o table

# List all resource groups and locations
az group list --query "[].{Name:name, Location:location}" -o table
```

### Step 2: Inspect Existing West US SQL Server & Database
```bash
# List SQL servers in West US
az sql server list --query "[?location=='westus' || location=='westus2' || location=='westus3'].{Name:name, ResourceGroup:resourceGroup, Location:location, FQDN:fullyQualifiedDomainName}" -o table

# List databases on your server (replace <server-name> and <resource-group>)
az sql db list -g <resource-group> -s <server-name> --query "[].{Database:name, Status:status, Tier:sku.name, MaxSizeGB:maxSizeBytes}" -o table
```

### Step 3: Inspect Existing East US Resources (App, Logs, AI)
```bash
# List resources in East US
az resource list --location eastus --query "[].{Name:name, Type:type, ResourceGroup:resourceGroup}" -o table

# Check if a Container Apps Environment or Container Registry already exists
az containerapp env list -o table
az acr list --query "[].{Name:name, ResourceGroup:resourceGroup, Location:location, Sku:sku.name}" -o table

# Verify AI Foundry deployment (<AI_RESOURCE>)
az cognitiveservices account list --query "[?contains(name, 'assessment')].{Name:name, Location:location, Endpoint:properties.endpoint}" -o table
```

---

## 8. Alternative: Azure Portal UI Inspection Instructions

If Cloud Shell is restricted on your organization laptop, you can inspect these details directly in the **Azure Portal UI**:

1. **SQL Database (West US):**
   - Navigate to **SQL databases** in the search bar.
   - Note the **Database name**, **Server name**, **Resource group**, and **Pricing tier** (e.g., Basic, S0).
   - Under the SQL Server blade, click **Networking** → check if *"Allow Azure services and resources to access this server"* is checked.
2. **AI Foundry / OpenAI (East US):**
   - Navigate to **Azure AI Services** or **Cognitive Services**.
   - Confirm `<AI_RESOURCE>` exists in East US.
   - Click **Model deployments** → confirm deployment `gpt-4o` is active.
3. **Application & Monitoring (East US):**
   - Navigate to **Log Analytics workspaces** and **Application Insights** → note their names and resource groups.
   - Check if an **Azure Container Registry** (ACR) or **Container App Environment** is already created.

---

## 9. Resource-by-Resource Phase 1 Provisioning Plan (Upon Your Approval)

Once you provide the names of the existing resources from the inspection above, Phase 1 will be executed as follows:

| Step | Resource | Action | Location | Execution Channel |
|---|---|---|---|---|
| **1.1** | **Resource Group** | Reuse existing East US resource group or create `rg-assessment-mvp` | East US | Cloud Shell script |
| **1.2** | **SQL Server Firewall** | Add `AllowAzureServices` rule to existing West US SQL Server | West US | Cloud Shell script |
| **1.3** | **SQL App User** | Create least-privilege `assess_app` user (no admin password in apps) | West US | Script via Cloud Shell |
| **1.4** | **Log Analytics & Insights** | Wire existing East US App Insights connection string | East US | Cloud Shell / Portal |
| **1.5** | **AI Foundry (GPT-4o)** | Wire `<AI_RESOURCE>` deployment endpoint | East US | Cloud Shell / Portal |
| **1.6** | **Storage Account** | Verify/create standard LRS Storage Account + `jd-files` private container | East US | Cloud Shell script |
| **1.7** | **Communication Services** | Provision ACS with Azure-managed domain | East US / US | Cloud Shell script |
| **1.8** | **Container Registry & Apps** | Provision Basic ACR + Container Apps Environment + `assess-api` | East US | Cloud Shell script |
| **1.9** | **Budget Alert** | Configure $25.00/month budget alert at 50%, 80%, 100% | Subscription | Cloud Shell script |
| **1.10** | **Live Smoke Test** | Run non-destructive health checks against deployed services | East US / West US | Cloud Shell script |

---

## 10. Next Steps

1. Run the inspection commands in Section 7 from your organization laptop's Azure Cloud Shell (or follow Section 8 in the Portal).
2. Share the non-sensitive output (resource names, existing resource groups, and SKUs).
3. Review and approve the plan, and we will generate the exact, ready-to-execute Phase 1 provisioning script for your Cloud Shell.

