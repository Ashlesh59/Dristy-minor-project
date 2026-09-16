# Deploying InvestIQ to Vercel and Neon

This document outlines the exact steps to deploy InvestIQ using Vercel (for the frontend and serverless Python backend) and Neon (for the Serverless Postgres database).

## 1. Push the Feature Branch
- Push the current `feature/vercel-neon-deployment` branch to your GitHub repository.
- Do NOT merge into `main` yet. We will test the preview deployment first.

## 2. Create the Vercel Project
- Log in to your Vercel dashboard and click **Add New** -> **Project**.
- Select your InvestIQ GitHub repository.
- Leave the framework preset as **Other** (Vercel automatically detects `vercel.json` and `api/index.py`).
- Do not click "Deploy" yet.

## 3. Connect Neon Postgres
- In the Vercel project configuration, go to the **Storage** tab.
- Click **Create Database** and select **Neon Postgres**.
- Follow the prompts to create the database instance.
- Vercel will automatically inject the `DATABASE_URL` environment variable into your project.

## 4. Configure Preview Environment Variables
Before deploying, ensure the following environment variables are set in your Vercel project settings (**Settings** -> **Environment Variables**):
- `DATABASE_URL`: Automatically managed by the Neon integration.
- `SECRET_KEY`: A strong, randomly generated string. (Generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
- `GEMINI_API_KEY`: Your valid Google Gemini API key.
- `CORS_ALLOWED_ORIGINS`: Your Vercel preview domain (Vercel automatically includes `VERCEL_URL` now, but it's good practice to set it).
- `ALPHA_VANTAGE_API_KEY`: (Optional) Required if you plan to use live Alpha Vantage fallback features.

## 5. Run a Preview Deployment
- Go to the **Deployments** tab.
- Find the latest commit on your `feature/vercel-neon-deployment` branch.
- Click **Deploy** or trigger a new preview deployment for this specific branch.
- Wait for Vercel to build the frontend assets and deploy the Flask backend as serverless functions.

## 6. Test the Preview
Verify the deployment by visiting the health endpoint on your preview URL:
```
https://<your-preview-branch-domain>.vercel.app/api/health
```
You should receive a `200 OK` JSON response.

### Seed Official NSE Company Data
The Neon database starts completely empty. You must seed the official NSE master data manually using the CLI.
Execute the following PowerShell script locally, ensuring you substitute the correct connection string:
```powershell
$env:DATABASE_URL="<your_neon_database_url_from_vercel>"
.\scripts\seed_production.ps1 -ConfirmProductionWrite
```

After the data is seeded, log into the preview URL. Search for an existing NSE company, create research, and fetch market data.

## 7. Merge into Main
Only after you have fully verified the preview deployment (successful login, company search, research generation, and market data retrieval):
- Open a Pull Request from `feature/vercel-neon-deployment` into `main`.
- Approve and merge the branch.

## 8. Promote to Production
- Merging into `main` will automatically trigger a Vercel production deployment.
- Verify that your production URL is working smoothly.
