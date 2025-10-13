# Railway Volume Setup Guide

## Why Use a Persistent Volume?

Railway containers are ephemeral - when you deploy a new version, the container is rebuilt from scratch. This means any files written to the container's filesystem (like `guild_configs.json`) are lost with each deployment.

A **persistent volume** solves this by providing storage that survives across deployments and container restarts.

## Setup Instructions

### 1. Add a Volume in Railway

1. Go to your Railway project dashboard
2. Select your OPSObot service
3. Click the **"Variables"** tab
4. Scroll down to the **"Volume"** section (or click "Storage" in the sidebar)
5. Click **"Add Volume"** or **"New Volume"**
6. Configure the volume:
   - **Mount Path**: `/data` (must be exactly this)
   - **Volume Size**: 1GB is sufficient (can increase if needed)
7. Click **"Add"** or **"Create"**

### 2. Redeploy Your Service

After adding the volume, Railway will automatically redeploy your service. The bot will now:
- Store guild configurations in `/data/guild_configs.json`
- Persist all configurations across new deployments
- Continue working even after updates to your code

### 3. Verify It's Working

Check your Railway logs after deployment. You should see:
```
Using configuration file: /data/guild_configs.json
Data directory: /data
```

## How It Works

The bot automatically detects whether `/data` exists:
- **With volume**: Uses `/data/guild_configs.json`
- **Without volume (local dev)**: Uses `./guild_configs.json`

This means you can develop locally without needing to create a `/data` directory.

## Alternative: Redis (Not Implemented)

The user mentioned using Redis in the past. While Redis is a great option for data persistence, it:
- Requires additional service setup and costs
- Needs code changes to use Redis client
- Is more complex for simple configuration storage

For this bot's needs, a simple volume is more appropriate since:
- Configuration data is small (just JSON)
- No need for complex queries or caching
- Simpler to maintain and backup
- Lower cost (included in Railway plan)

## Backup and Recovery

To backup your guild configurations:
1. Use Railway CLI to access your volume
2. Copy `/data/guild_configs.json` to your local machine
3. Store it securely

To restore configurations:
1. Upload the backup file to `/data/guild_configs.json` in your Railway volume
2. Restart the service

## Troubleshooting

### Configurations still being lost after deployment?
- Verify the volume mount path is exactly `/data` (case-sensitive)
- Check Railway logs for "Using configuration file: /data/guild_configs.json"
- Ensure the volume is attached to the correct service

### Permission errors?
- Railway should automatically handle permissions
- If issues persist, contact Railway support

### Need to reset configurations?
- Delete `/data/guild_configs.json` from the volume
- Restart the service
- Guilds will need to run `/setup` again
