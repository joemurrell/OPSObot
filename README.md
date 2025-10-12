# OPSObot 🎯

AI-powered Discord bot for DCS Squadron Standard Operating Procedures (SOPs). Built with OpenAI Assistants API, OPSObot is a **hosted service** that helps squadrons upload their SOP documents and provides interactive Q&A and quiz functionality to keep members sharp on procedures.

## Features

- **Hosted Service**: Centralized API key management - no need for users to provide their own OpenAI keys
- **Per-Server Isolation**: Each Discord server gets its own dedicated vector store for complete document isolation
- **Document Upload**: Admins can upload various document types (PDF, Word, PowerPoint, text, images) that the bot uses to answer questions
- **Q&A System**: Ask questions about your SOPs and get answers grounded in your uploaded documents
- **Quiz System**: Generate timed quizzes from your SOP documents to test squadron knowledge
- **Intelligent Responses**: Powered by GPT-4 with vector search for accurate, citation-backed answers
- **Monetization Ready**: Architecture supports subscription tiers and premium features

## Architecture

### Centralized Management
- Single OpenAI API key controlled by bot owner
- Reduces complexity for end users
- Enables hosted SaaS model with potential for premium tiers

### Per-Guild Isolation
- Each Discord server gets its own OpenAI Assistant
- Each server has a dedicated Vector Store for documents
- **Zero cross-contamination**: Server A's documents are never accessible to Server B
- Documents are tagged and isolated at the vector store level

## Setup

### Prerequisites

- Discord bot token ([Create a bot](https://discord.com/developers/applications))
- OpenAI API key (bot owner provides this - users don't need their own)
- Python 3.11+

### Installation

1. Clone the repository:
```bash
git clone https://github.com/joemurrell/OPSObot.git
cd OPSObot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set environment variables:
```bash
export DISCORD_TOKEN="your-discord-bot-token"
export OPENAI_API_KEY="your-openai-api-key"  # Bot owner's key
```

4. Run the bot:
```bash
python app.py
```

### Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section and create a bot
4. Enable these Privileged Gateway Intents:
   - Message Content Intent
5. Go to "OAuth2" > "URL Generator"
6. Select scopes: `bot`, `applications.commands`
7. Select bot permissions:
   - Send Messages
   - Embed Links
   - Read Message History
   - Use Slash Commands
8. Use the generated URL to invite the bot to your server

## Usage

### Server Configuration (Admin Only)

1. **Initialize the bot for your server**:
```
/setup
```
This creates a dedicated OpenAI Assistant and isolated vector store for your server. No API key needed from you!

2. **Upload SOP documents**:
```
/upload document:<attach-file>
```
Upload your squadron's SOP documents. The bot will process and index them in your server's private vector store.

**Supported file types**:
- **Documents**: PDF, Word (.doc, .docx)
- **Presentations**: PowerPoint (.ppt, .pptx)
- **Text**: TXT, Markdown (.md)
- **Images**: JPG, PNG, GIF, BMP, WebP

3. **View uploaded documents**:
```
/list_documents
```

4. **Remove a document** (if needed):
```
/remove_document file_id:<file-id-from-list>
```

### Using the Bot

**Ask questions about your SOPs**:
```
/ask question:What is the standard radio frequency for tower?
```

**Start a quiz**:
```
/quiz_start questions:6 duration:5 topic:radio procedures
```
- `questions`: Number of questions (1-10)
- `duration`: Quiz duration in minutes (1-60)
- `topic`: Optional topic focus

**Check your quiz progress**:
```
/quiz_score
```

**End a quiz early**:
```
/quiz_end
```

**View bot information**:
```
/info
```

## How It Works

1. **Centralized API**: Bot owner provides a single OpenAI API key
2. **Per-Guild Setup**: Each Discord server runs `/setup` to create their own Assistant and Vector Store
3. **Document Isolation**: Uploaded documents go into the server's dedicated vector store
4. **Grounded Responses**: All answers use only documents from that server's vector store
5. **Quiz Generation**: AI generates diverse multiple-choice questions from server-specific documents

## Security & Privacy

- **API Key**: Centrally managed by bot owner - users never handle OpenAI credentials
- **Document Isolation**: Each server's documents are stored in a separate vector store
- **No Cross-Contamination**: Vector store IDs ensure complete data separation between servers
- **Admin Controls**: Only server administrators can configure and upload documents
- **File Type Security**: Only safe document types allowed (no executable code or scripts)
- **Local Config**: Server configurations stored in `guild_configs.json` (persisted with git repository)

## Monetization Model

The architecture supports various monetization strategies:

- **Free Tier**: Basic setup with limited documents/queries
- **Premium Tier**: Unlimited documents, priority support, advanced features
- **Enterprise**: Custom integrations, dedicated support, SLA guarantees

The centralized API key model allows the bot owner to:
- Track usage per guild
- Implement rate limiting
- Enforce tier limits
- Bill based on actual usage

## Deployment

### Railway

The bot includes a `railway.json` and `Dockerfile` for easy deployment:

1. Connect your GitHub repo to Railway
2. Set the `DISCORD_TOKEN` and `OPENAI_API_KEY` environment variables
3. Deploy!

Each guild will still need to run `/setup` to initialize their assistant and vector store.

**Configuration Persistence**: Guild configurations are stored in `guild_configs.json` which is now tracked in git. This ensures that server setups persist across deployments and restarts. The bot will automatically load existing configurations on startup.

## Technical Details

- **Discord.py**: Discord bot framework with slash commands
- **OpenAI Assistants API v2**: AI-powered Q&A with file search capability
- **Vector Stores**: Document embeddings for semantic search (see `guild_configs.example.json` for structure)
- **JSON Storage**: Simple file-based storage for guild configurations

## License

MIT License - see LICENSE file

## Contributing

Contributions welcome! Please open an issue or PR.

## Support

For issues or questions, please open a GitHub issue.

## Troubleshooting

### Bot doesn't respond to commands
- Ensure the bot has been added to your server with the correct permissions
- Run `/info` to check if the server is configured
- Check that the bot has permissions in the channel (Send Messages, Embed Links, etc.)

### `/setup` fails
- Verify the `OPENAI_API_KEY` environment variable is set correctly (bot owner)
- Check that you have access to the Assistants API (may require a paid OpenAI account)
- Ensure you're running the command in a server (not DMs) and have Administrator permissions

### `/upload` fails
- Check that your file type is supported (PDF, Word, PowerPoint, text, or image files)
- Verify your OpenAI account has sufficient storage quota
- Ensure the file isn't too large (OpenAI has file size limits)
- For security, only common document types are allowed (no .py, .exe, .sh, etc.)

### Questions return "not configured" error
- An admin needs to run `/setup` first to initialize the server
- Check that documents have been uploaded with `/upload`
- Try `/info` to see the server's configuration status

### Quiz questions are repetitive
- Upload more diverse SOP documents
- Try specifying a `topic` parameter in `/quiz_start` to focus on specific areas
- The bot attempts to generate diverse questions, but limited source material may result in similar questions

### Documents from other servers appearing
- This should never happen! Each server has its own isolated vector store
- If you experience this, please report it immediately as it's a critical bug
