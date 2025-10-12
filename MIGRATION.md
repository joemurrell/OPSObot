# Migration Guide: Moving to Persistent Volume Storage

If you're upgrading from a previous version that stored `guild_configs.json` in the git repository, follow this guide to migrate to the new persistent volume storage.

## Why This Change?

Previously, `guild_configs.json` was committed to git to persist across deployments. This approach had issues:
- Git conflicts when multiple deployments tried to update the file
- Configuration changes would trigger unnecessary git commits
- Security concern: sensitive IDs stored in version control

The new approach uses Railway's persistent volumes for cleaner, more reliable storage.

## Migration Steps

### Step 1: Backup Your Current Configuration

Before making any changes, save your current `guild_configs.json`:

1. In your Railway dashboard, access the logs or use Railway CLI
2. Copy the contents of your current `guild_configs.json` file
3. Save it locally as `guild_configs_backup.json`

### Step 2: Set Up the Volume

Follow the instructions in [RAILWAY_VOLUME_SETUP.md](./RAILWAY_VOLUME_SETUP.md):
1. Add a new volume with mount path `/data`
2. Size: 1GB is sufficient
3. Wait for Railway to redeploy

### Step 3: Restore Your Configuration

After the volume is set up and the service is running:

1. Access your Railway service via CLI:
   ```bash
   railway link
   railway shell
   ```

2. Copy your backup configuration to the volume:
   ```bash
   cat > /data/guild_configs.json << 'EOF'
   # Paste your backup configuration here
   EOF
   ```

3. Verify the file exists:
   ```bash
   cat /data/guild_configs.json
   exit
   ```

4. Restart your service in Railway dashboard

### Step 4: Verify Migration

1. Check Railway logs for:
   ```
   Using configuration file: /data/guild_configs.json
   Data directory: /data
   Loaded N guild configuration(s)
   ```

2. Test a Discord command (like `/info`) to ensure guilds are still configured

3. Try a new command (like `/ask`) to ensure the bot is working correctly

## If You Don't Have Existing Configurations

If this is a fresh installation or you don't have any guild configurations to migrate:

1. Just set up the volume as described in [RAILWAY_VOLUME_SETUP.md](./RAILWAY_VOLUME_SETUP.md)
2. Deploy the new version
3. Guilds will need to run `/setup` to initialize their configurations

The bot will automatically create a new `guild_configs.json` in the `/data` volume.

## Rollback Plan

If you need to rollback to the previous version:

1. Checkout the previous commit:
   ```bash
   git checkout <previous-commit-hash>
   ```

2. Deploy that version to Railway

3. Your configurations will be back in the git-tracked `guild_configs.json`

Note: You'll lose any configurations made while running the new version unless you manually merge them.

## Questions?

If you encounter issues during migration, check:
- Railway logs for error messages
- Volume is correctly mounted at `/data`
- File permissions in the volume

For additional help, open an issue on GitHub.
