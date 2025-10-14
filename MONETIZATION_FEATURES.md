# Monetization Features Implementation

## Overview

This document describes the monetization features implemented for OPSObot using Discord's native monetization system.

## Limits Overview

### Free Tier Limits

| Feature | Limit | Reset Period |
|---------|-------|--------------|
| File Upload Size | 5 MB | Per upload |
| `/ask` Command | 3 queries | Daily (midnight UTC) |
| `/quiz_start` Command | 1 quiz | Daily (midnight UTC) |

### Premium Tier Benefits

| Feature | Premium Limit |
|---------|---------------|
| File Upload Size | 50 MB |
| `/ask` Command | Unlimited |
| `/quiz_start` Command | Unlimited |

## Implementation Details

### File Size Limits

Instead of counting pages (which doesn't work for all document types), the bot uses **file size** as the limiting factor:

- **Why file size?** Works uniformly across all supported document types (PDF, Word, PowerPoint, text, images, markdown)
- **Free tier:** 5 MB maximum
- **Premium tier:** 50 MB maximum
- **Check location:** `/upload` command, before uploading to OpenAI

### Usage Tracking

Daily usage is tracked per-user, per-guild in the persistent `guild_configs.json` file:

```json
{
  "guild_id": {
    "usage_tracking": {
      "2025-10-14": {
        "user_id_123": {
          "asks": 2,
          "quizzes": 1
        }
      }
    }
  }
}
```

- Resets automatically at midnight UTC
- Old dates are cleaned up automatically (keeps today + yesterday)
- Persists across bot restarts via volume mount

### Premium Status Checking

The bot checks for premium status using Discord's entitlements API:

```python
async def check_premium_status(user_id: int) -> bool:
    """Check if a user has premium tier via Discord entitlements."""
```

- Requires `PREMIUM_SKU_ID` environment variable
- Falls back to free tier if not configured
- Checked in real-time for each command

## User Experience

### Free Tier User Hitting Limits

**File Upload (>5 MB):**
```
❌ File too large for free tier

• Your file: 7.2 MB
• Free tier limit: 5 MB

🌟 Upgrade to Premium for:
• Upload files up to 50 MB
• Unlimited /ask queries
• Unlimited quizzes
```

**Ask Command (3/3 used):**
```
❌ Daily limit reached (3/3 asks today)

🌟 Upgrade to Premium for:
• Unlimited /ask queries
• Unlimited quizzes
• Larger document uploads (up to 50 MB)

Your limit resets at midnight UTC.
```

**Quiz Command (1/1 used):**
```
❌ Daily limit reached (1/1 quiz today)

🌟 Upgrade to Premium for:
• Unlimited quizzes
• Unlimited /ask queries
• Larger document uploads (up to 50 MB)

Your limit resets at midnight UTC.
```

### Premium Tier User

Premium users experience no changes - all features work without limits.

## Configuration

### Environment Variables

```bash
# Required
DISCORD_TOKEN=your_discord_bot_token
OPENAI_API_KEY=your_openai_api_key

# Optional - for premium tier
PREMIUM_SKU_ID=your_discord_sku_id
```

### Setting up Discord Monetization

1. Go to Discord Developer Portal
2. Navigate to your application
3. Go to "Monetization" section
4. Create a SKU for your premium tier
5. Copy the SKU ID
6. Set `PREMIUM_SKU_ID` environment variable
7. Deploy the bot

## Testing

To test the limits without premium:
1. Don't set `PREMIUM_SKU_ID` (everyone is free tier)
2. Try uploading files >5 MB
3. Try using `/ask` more than 3 times in a day
4. Try using `/quiz_start` more than once in a day

## Future Enhancements

Potential future improvements:
- Multiple premium tiers with different limits
- Usage statistics dashboard
- Monthly usage reports
- Custom limits per guild
- Temporary trial periods
