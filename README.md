# OPSObot 🎯

AI-powered Discord bot for DCS Squadron Standard Operating Procedures (SOPs). Built with OpenAI Assistants API, OPSObot helps squadrons upload their SOP documents and provides interactive Q&A and quiz functionality to keep members sharp on procedures.

## Features

- **Multi-Guild Support**: Each Discord server can configure its own OpenAI API key and upload its own SOP documents
- **Document Upload**: Admins can upload PDF SOP documents that the bot uses to answer questions
- **Q&A System**: Ask questions about your SOPs and get answers grounded in your uploaded documents
- **Quiz System**: Generate timed quizzes from your SOP documents to test squadron knowledge
- **Intelligent Responses**: Powered by GPT-4 with vector search for accurate, citation-backed answers

## Setup

### Prerequisites

- Discord bot token ([Create a bot](https://discord.com/developers/applications))
- OpenAI API key (per server, configured after bot joins)
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
# Optional: Set a global fallback API key
export OPENAI_API_KEY="your-openai-api-key"
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

1. **Configure the bot for your server**:
```
/setup api_key:<your-openai-api-key>
```
This creates a dedicated OpenAI Assistant and vector store for your server.

2. **Upload SOP documents**:
```
/upload document:<attach-pdf-file>
```
Upload your squadron's SOP PDFs. The bot will process and index them.

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

1. **Per-Guild Configuration**: Each Discord server gets its own OpenAI Assistant and vector store
2. **Document Processing**: Uploaded PDFs are sent to OpenAI's vector store for semantic search
3. **Grounded Responses**: All answers are grounded in the uploaded documents with page citations
4. **Quiz Generation**: The AI generates diverse multiple-choice questions from document content
5. **Interactive Quizzes**: Timed quizzes with button-based answers and automatic scoring

## Architecture

- **Discord.py**: Discord bot framework with slash commands
- **OpenAI Assistants API v2**: AI-powered Q&A with file search capability
- **Vector Stores**: Document embeddings for semantic search
- **JSON Storage**: Simple file-based storage for guild configurations

## Security Notes

- API keys are stored locally in `guild_configs.json`
- Each guild's API key is only used for that guild's operations
- Admin permissions required for setup and document uploads
- Documents are stored in OpenAI's secure infrastructure

## Deployment

### Railway

The bot includes a `railway.json` and `Dockerfile` for easy deployment:

1. Connect your GitHub repo to Railway
2. Set the `DISCORD_TOKEN` environment variable
3. Deploy!

Guilds will still need to configure their own API keys using `/setup`.

## License

MIT License - see LICENSE file

## Contributing

Contributions welcome! Please open an issue or PR.

## Support

For issues or questions, please open a GitHub issue.

