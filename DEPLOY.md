# Provera - Railway Deployment Guide

## Architecture
```
Railway Project
├── provera-api (Backend - Python/FastAPI)
└── provera-frontend (Frontend - React/Vite)
```

## Step 1: Prepare Data Files

The backend needs these parquet files in `data/processed/`:
- `master_facilities.parquet` (11MB)
- `facility_features.parquet` (2MB)
- `master_ownership.parquet` (5MB)
- `medigraph.gpickle` (8MB)
- `facility_graph.gpickle` (4MB)

**Option A**: Upload to Railway volume
**Option B**: Host on S3/GCS and download on startup
**Option C**: Include in repo (if < 100MB total)

## Step 2: Deploy Backend

1. Go to [railway.app](https://railway.app)
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your repo, point to `/medigraph` folder
4. Railway will auto-detect Python and use `railway.toml`

**Set Environment Variables:**
```
ANTHROPIC_API_KEY=sk-ant-xxxxx
DATA_DIR=/app/data/processed
```

5. Note the generated URL: `https://provera-api-xxxx.railway.app`

## Step 3: Deploy Frontend

1. In same Railway project, click "New Service"
2. Select same repo, but set **Root Directory** to `medigraph/frontend`
3. Railway will auto-detect Node.js

**Set Environment Variables:**
```
VITE_API_URL=https://provera-api-xxxx.railway.app/api
NODE_ENV=production
```

4. Frontend URL: `https://provera-frontend-xxxx.railway.app`

## Step 4: Connect Services

Railway auto-assigns URLs. Update frontend's `VITE_API_URL` to point to backend.

## Quick Deploy Commands (CLI)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Deploy backend
cd medigraph
railway init
railway up

# Deploy frontend (separate service)
cd frontend
railway init
railway up
```

## Environment Variables Summary

### Backend (provera-api)
| Variable | Value |
|----------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `DATA_DIR` | `/app/data/processed` |
| `PORT` | (auto-set by Railway) |

### Frontend (provera-frontend)
| Variable | Value |
|----------|-------|
| `VITE_API_URL` | `https://your-backend.railway.app/api` |
| `NODE_ENV` | `production` |

## Data Upload Options

### Option 1: Git LFS (Recommended for < 100MB)
```bash
git lfs install
git lfs track "*.parquet"
git lfs track "*.gpickle"
git add .gitattributes
git add data/processed/
git commit -m "Add data files via LFS"
```

### Option 2: Railway Volume
1. Create volume in Railway dashboard
2. Mount at `/app/data/processed`
3. Upload files via Railway CLI or SFTP

### Option 3: S3 + Download on Startup
Add to `api.py`:
```python
import boto3
# Download from S3 on startup
```

## Estimated Costs

| Service | Railway Plan | Monthly |
|---------|-------------|---------|
| Backend | Hobby ($5) | ~$5-10 |
| Frontend | Hobby ($5) | ~$2-5 |
| **Total** | | **~$7-15/mo** |

## Troubleshooting

**Build fails?**
- Check `requirements.txt` has all deps
- Ensure Python 3.11 compatibility

**API not responding?**
- Check `/api/health` endpoint
- Verify data files are present
- Check Railway logs

**Frontend can't reach API?**
- Verify `VITE_API_URL` is correct
- Check CORS settings in `api.py`

## CORS Configuration

Add to `api.py` if not present:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specific frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
