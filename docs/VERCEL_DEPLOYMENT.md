# Deploying InvestIQ to Vercel and Neon

This document outlines the exact steps to deploy InvestIQ using Vercel (for the frontend and serverless Python backend) and Neon (for the Serverless Postgres database).

## 1. Create the Vercel Project
- Push the latest `main` branch to your GitHub repository.
- Log in to your Vercel dashboard and click **Add New** -> **Project**.
- Select your InvestIQ GitHub repository.
- Leave the framework preset as **Other** (Vercel automatically detects the `vercel.json` and `api/index.py`).
- Do not click "Deploy" yet; first configure the environment and database.

## 2. Connect Neon Postgres
- In the Vercel project configuration, go to the **Storage** tab.
- Click **Create Database** and select **Neon Postgres**.
- Follow the prompts to create the database instance.
- Vercel will automatically inject the `DATABASE_URL` environment variable into your project.

## 3. Configure Environment Variables
Before deploying, ensure the following environment variables are set in your Vercel project settings (**Settings** -> **Environment Variables**):
- `DATABASE_URL`: Automatically managed by the Neon integration.
- `SECRET_KEY`: A strong, randomly generated string.
- `GEMINI_API_KEY`: Your valid Google Gemini API key.
- `CORS_ALLOWED_ORIGINS`: The exact origin of your Vercel deployment (see Step 5).
- `ALPHA_VANTAGE_API_KEY`: (Optional) Required if you plan to use live Alpha Vantage fallback features.

## 4. Generate a Strong SECRET_KEY
Generate a secure random key using Python:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Copy the output and use it as your `SECRET_KEY` value in Vercel.

## 5. Set the Production Origin
Your frontend needs to know where the API is hosted, and the backend needs to know which origin is allowed for CORS.
- Once you know your preview or production URL (e.g., `https://investiq.vercel.app`), set `CORS_ALLOWED_ORIGINS` to `https://investiq.vercel.app`.
- Ensure there is no trailing slash or wildcard.

## 6. Create a Preview Deployment
- After saving the environment variables, go to the **Deployments** tab.
- Find your latest commit on the preview branch and click **Redeploy** or trigger a new deployment.
- Vercel will build the frontend assets and deploy the Flask backend as serverless functions.

## 7. Test API Health
Verify the deployment by visiting the health endpoint:
```
https://<your-vercel-domain>.vercel.app/api/health
```
You should receive a `200 OK` JSON response indicating `success: true` and `status: "healthy"`.

## 8. Seed Official NSE Company Data
The Neon database starts completely empty. You must seed the official NSE master data manually using the CLI.
Execute the following PowerShell script locally, ensuring you substitute the correct connection string:
```powershell
$env:DATABASE_URL="<your_neon_database_url_from_vercel>"
.\scripts\seed_production.ps1 -ConfirmProductionWrite
```
**Important:** Never upload the `EQUITY_L.csv` file to Git. Keep it safely in your local `data/raw/` folder.

## 9. Confirm Database Persistence
After the data is seeded, log into the Vercel URL. Search for an existing NSE company to confirm that data was correctly seeded to the Postgres database. Redeploy the app from Vercel to verify that the search index and users persist across stateless function restarts.

## 10. Inspect Vercel Function Logs
If you encounter 500 errors or issues:
- Go to the **Logs** tab in your Vercel project.
- Filter by `api/index.py` to see the Flask backend logs.
- This is the safest way to view exception stack traces, as InvestIQ never leaks internal errors to the client UI.

## 11. Roll Back a Deployment
If an issue is found in a deployment:
- Go to the **Deployments** tab.
- Click the three dots next to a previous, stable deployment.
- Select **Promote to Production** or **Redeploy**.

## 12. Promote to Production
Once you have fully verified the preview deployment (successful login, company search, research generation, and market data retrieval):
- Open a Pull Request from `feature/vercel-neon-deployment` into `main`.
- Merge the branch.
- Vercel will automatically build and deploy `main` to your primary production domain.
