# Deploying PolicyPilot to Google Cloud Run

Two Cloud Run services (API and web app), two Cloud Run jobs (migrations and demo seed),
images in Artifact Registry, secrets in Secret Manager, and managed databases outside GCP.

```mermaid
flowchart LR
  user([Browser]) --> web[Cloud Run: policypilot-web<br/>Next.js standalone]
  user -->|fetch / SSE| api[Cloud Run: policypilot-api<br/>FastAPI + uvicorn]
  api --> pg[(Neon Postgres<br/>+ pgvector)]
  api --> mongo[(MongoDB Atlas)]
  api --> llm{{OpenAI / Anthropic / Gemini}}
  sm[Secret Manager] -.-> api
  jobs[Cloud Run jobs:<br/>migrate, seed] --> pg
```

> These commands follow the current gcloud CLI documentation but have not yet been run against
> a live project from this repository. Run them step by step and check each output.

## 1. Databases

Both are configured with environment variables, so any of these options works without code
changes.

| Option | Pros | Cons |
| --- | --- | --- |
| **Neon** (recommended) | Serverless Postgres with pgvector built in; free tier; scales to zero | Cold start of about a second after idle; free tier storage is small |
| Supabase | pgvector included; free tier; dashboard | Free projects pause after a week without activity |
| Cloud SQL for PostgreSQL | Inside GCP; private networking; no egress | No free tier (smallest instance costs money every hour); more setup (Cloud SQL connector / VPC) |
| **MongoDB Atlas M0** (logs + history) | Free; MongoDB 7+ (the Admin page needs `$percentile`) | 512 MB; Cloud Run has no fixed egress IP, so allow `0.0.0.0/0` with a strong password, or add Cloud NAT with a static IP |

**Neon**: create a project and enable the extension (`CREATE EXTENSION IF NOT EXISTS vector;`
also runs in the first migration). Use the **direct** connection string, not the pooled
(`-pooler`) one: PgBouncer in transaction mode breaks asyncpg's prepared statements. asyncpg
takes `ssl=require`, not `sslmode`:

```
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@ep-xxxx.REGION.aws.neon.tech/neondb?ssl=require
```

**Atlas**: create an M0 cluster and a database user, then copy the `mongodb+srv://` string:

```
MONGO_URL=mongodb+srv://USER:PASSWORD@cluster0.xxxx.mongodb.net/?retryWrites=true&w=majority
```

## 2. Project setup

```bash
export PROJECT_ID=your-project-id
export REGION=asia-south1                      # Mumbai; any Cloud Run region works
export REPO=policypilot
export IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO
export RUN_SA=policypilot-run@$PROJECT_ID.iam.gserviceaccount.com

gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com secretmanager.googleapis.com iamcredentials.googleapis.com

gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION

# Runtime identity for the services and jobs: it can only read their secrets.
gcloud iam service-accounts create policypilot-run --display-name="PolicyPilot runtime"
```

## 3. Secrets

Keys and connection strings never go into images, env files or the repository.

```bash
for name in openai-api-key anthropic-api-key gemini-api-key database-url mongo-url; do
  gcloud secrets create $name --replication-policy=automatic
done

printf '%s' "sk-..."            | gcloud secrets versions add openai-api-key    --data-file=-
printf '%s' "sk-ant-..."        | gcloud secrets versions add anthropic-api-key --data-file=-
printf '%s' "AIza..."           | gcloud secrets versions add gemini-api-key    --data-file=-
printf '%s' "$DATABASE_URL"     | gcloud secrets versions add database-url      --data-file=-
printf '%s' "$MONGO_URL"        | gcloud secrets versions add mongo-url         --data-file=-

for name in openai-api-key anthropic-api-key gemini-api-key database-url mongo-url; do
  gcloud secrets add-iam-policy-binding $name \
    --member=serviceAccount:$RUN_SA --role=roles/secretmanager.secretAccessor
done
```

Shared settings for the API and the jobs:

```bash
export SECRETS="OPENAI_API_KEY=openai-api-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest,DATABASE_URL=database-url:latest,MONGO_URL=mongo-url:latest"
export ENV_VARS="ENVIRONMENT=production,EMBEDDING_PROVIDER=openai,EMBEDDING_MODEL=text-embedding-3-small,EMBEDDING_DIM=1536,OPENAI_CHAT_MODEL=gpt-5.4-mini,ANTHROPIC_CHAT_MODEL=claude-haiku-5-5,GEMINI_CHAT_MODEL=gemini-2.5-flash,DEFAULT_LLM_PROVIDER=openai"
```

## 4. Backend image, migrations, API

```bash
export TAG=v1
gcloud builds submit backend --tag $IMAGE/backend:$TAG       # builds the Dockerfile's prod stage

# Migrations run as a one-off job, not on every container start.
gcloud run jobs create policypilot-migrate --image $IMAGE/backend:$TAG --region $REGION \
  --service-account $RUN_SA --set-secrets "$SECRETS" --set-env-vars "$ENV_VARS" \
  --command alembic --args upgrade,head --max-retries 0
gcloud run jobs execute policypilot-migrate --region $REGION --wait

gcloud run deploy policypilot-api --image $IMAGE/backend:$TAG --region $REGION \
  --service-account $RUN_SA --allow-unauthenticated \
  --set-secrets "$SECRETS" --set-env-vars "$ENV_VARS" \
  --memory 1Gi --cpu 1 --concurrency 40 --timeout 600 \
  --min-instances 0 --max-instances 3 --no-cpu-throttling

export API_URL=$(gcloud run services describe policypilot-api --region $REGION --format='value(status.url)')
curl $API_URL/health
```

`--no-cpu-throttling` keeps CPU allocated after a response is sent. Ingestion and contract
reviews run as background tasks after the request returns; with the default request-based
CPU they would stall. `--timeout 600` covers long streamed answers.

## 5. Frontend

`NEXT_PUBLIC_API_URL` is compiled into the browser bundle, so the image is built after the API
URL is known:

```bash
gcloud builds submit frontend --config deploy/cloudbuild.frontend.yaml \
  --substitutions _IMAGE=$IMAGE/frontend:$TAG,_API_URL=$API_URL

gcloud run deploy policypilot-web --image $IMAGE/frontend:$TAG --region $REGION \
  --allow-unauthenticated --memory 512Mi --cpu 1 --min-instances 0 --max-instances 3

export WEB_URL=$(gcloud run services describe policypilot-web --region $REGION --format='value(status.url)')
```

## 6. CORS and demo data

Allow the web app's origin on the API (the `^@^` prefix changes gcloud's list delimiter so the
JSON value survives):

```bash
gcloud run services update policypilot-api --region $REGION \
  --update-env-vars "^@^CORS_ORIGINS=[\"$WEB_URL\"]"
```

Load the fictional demo corpus (the job writes the sample PDFs itself, then ingests them):

```bash
gcloud run jobs create policypilot-seed --image $IMAGE/backend:$TAG --region $REGION \
  --service-account $RUN_SA --set-secrets "$SECRETS" \
  --set-env-vars "$ENV_VARS,SAMPLE_DATA_DIR=/tmp/sample_data" \
  --command python --args=-m,app.scripts.seed --max-retries 0
gcloud run jobs execute policypilot-seed --region $REGION --wait
```

Open `$WEB_URL`. The Admin page fills up as soon as you chat or run a review.

## 7. Releasing new versions

Manually:

```bash
export TAG=v2
gcloud builds submit backend --tag $IMAGE/backend:$TAG
gcloud run jobs update policypilot-migrate --image $IMAGE/backend:$TAG --region $REGION
gcloud run jobs execute policypilot-migrate --region $REGION --wait
gcloud run deploy policypilot-api --image $IMAGE/backend:$TAG --region $REGION
gcloud builds submit frontend --config deploy/cloudbuild.frontend.yaml \
  --substitutions _IMAGE=$IMAGE/frontend:$TAG,_API_URL=$API_URL
gcloud run deploy policypilot-web --image $IMAGE/frontend:$TAG --region $REGION
```

Or push a tag (`git tag v2 && git push origin v2`) and let
[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) do the same. It signs in to
Google Cloud with **Workload Identity Federation**: GitHub issues a short-lived OIDC token, and no
service account key is ever created or stored.

### One-time setup for the deploy workflow

```bash
export GITHUB_REPO=SanchitSlayer/policypilot
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export DEPLOY_SA=policypilot-deploy@$PROJECT_ID.iam.gserviceaccount.com

gcloud iam service-accounts create policypilot-deploy --display-name="PolicyPilot GitHub deploy"
for role in roles/run.admin roles/cloudbuild.builds.editor roles/artifactregistry.writer \
            roles/storage.admin roles/serviceusage.serviceUsageConsumer roles/logging.viewer; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$DEPLOY_SA --role=$role
done
# The deployer may run services and jobs as the runtime account.
gcloud iam service-accounts add-iam-policy-binding $RUN_SA \
  --member=serviceAccount:$DEPLOY_SA --role=roles/iam.serviceAccountUser

gcloud iam workload-identity-pools create github --location=global --display-name="GitHub"
gcloud iam workload-identity-pools providers create-oidc policypilot --location=global \
  --workload-identity-pool=github --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='$GITHUB_REPO'"
gcloud iam service-accounts add-iam-policy-binding $DEPLOY_SA \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$GITHUB_REPO"
```

Then add these repository **variables** (Settings → Secrets and variables → Actions →
Variables). They are identifiers, not secrets:

| Variable | Value |
| --- | --- |
| `GCP_PROJECT_ID` | `$PROJECT_ID` |
| `GCP_REGION` | `$REGION` |
| `GCP_WIF_PROVIDER` | `projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/policypilot` |
| `GCP_DEPLOY_SA` | `$DEPLOY_SA` |

The workflow assumes the services and jobs from steps 4–6 already exist (it updates images, it
does not recreate configuration).

## Production notes

- **Background work**: ingestion and reviews run in-process after the response. That is fine
  for a demo with `--no-cpu-throttling`; at scale, move them to Cloud Tasks or Cloud Run jobs so
  a scale-down cannot interrupt them.
- **Rate limits** are per instance by default (`RATE_LIMIT_STORAGE_URI=memory://`). With more
  than one instance, point it at Redis (Memorystore) to share counts.
- **Auth**: the demo is public. Add authentication (Identity-Aware Proxy, or an auth provider in
  the web app) before loading any real customer documents.
- **Costs**: Cloud Run scales to zero; Neon and Atlas free tiers cover a demo. LLM usage and
  estimated cost are visible on the Admin page.
