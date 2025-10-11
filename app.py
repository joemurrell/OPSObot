"""
OPSObot - DCS Squadron SOP Discord Bot
Multi-guild PDF-grounded Q&A and Quiz system using OpenAI Assistants API
Allows each Discord server to upload their own SOP documents and configure their own OpenAI API keys
"""
import os
import asyncio
import json
import re
import random
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Set, Tuple, Dict
from collections import Counter
import discord
from discord import app_commands
from openai import OpenAI
from fuzzywuzzy import fuzz

# Environment variables
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
# Global OpenAI API key is now optional - guilds can configure their own
GLOBAL_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# --- Discord client setup ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# --- Guild Configuration Storage ---
CONFIG_FILE = "guild_configs.json"

def load_guild_configs() -> Dict:
    """Load guild configurations from file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading guild configs: {e}")
            return {}
    return {}

def save_guild_configs(configs: Dict):
    """Save guild configurations to file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(configs, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving guild configs: {e}")

GUILD_CONFIGS = load_guild_configs()

def get_openai_client(guild_id: Optional[int]) -> Optional[OpenAI]:
    """
    Get OpenAI client for a specific guild.
    Returns None if guild is not configured.
    """
    if guild_id is None:
        # DM - use global key if available
        if GLOBAL_OPENAI_API_KEY:
            return OpenAI(
                api_key=GLOBAL_OPENAI_API_KEY,
                default_headers={"OpenAI-Beta": "assistants=v2"}
            )
        return None
    
    guild_key = str(guild_id)
    if guild_key in GUILD_CONFIGS and "api_key" in GUILD_CONFIGS[guild_key]:
        api_key = GUILD_CONFIGS[guild_key]["api_key"]
        return OpenAI(
            api_key=api_key,
            default_headers={"OpenAI-Beta": "assistants=v2"}
        )
    elif GLOBAL_OPENAI_API_KEY:
        # Fall back to global key
        return OpenAI(
            api_key=GLOBAL_OPENAI_API_KEY,
            default_headers={"OpenAI-Beta": "assistants=v2"}
        )
    
    return None

def get_assistant_id(guild_id: Optional[int]) -> Optional[str]:
    """Get the assistant ID for a specific guild."""
    if guild_id is None:
        return None
    
    guild_key = str(guild_id)
    if guild_key in GUILD_CONFIGS:
        return GUILD_CONFIGS[guild_key].get("assistant_id")
    
    return None

# Configure logging for Railway compatibility
# Railway prefers structured JSON logs with clear levels
# Reference: https://docs.railway.com/guides/logs
import sys

# Create logs directory for file logging
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)

# Configure logging with proper levels and formatting
# Railway will capture stdout/stderr and parse JSON if available
logging.basicConfig(
    level=logging.DEBUG,  # Capture all levels
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'darkstar.log')),
        logging.StreamHandler(sys.stdout)
    ]
)

# Create logger instances for different components
logger = logging.getLogger(__name__)
discord_logger = logging.getLogger('discord_bot')
quiz_logger = logging.getLogger('quiz')
api_logger = logging.getLogger('openai_api')

# Set levels for different loggers
logger.setLevel(logging.DEBUG)
discord_logger.setLevel(logging.DEBUG)
quiz_logger.setLevel(logging.DEBUG)
api_logger.setLevel(logging.INFO)

# In-memory quiz state (per-channel)
QUIZ_STATE = {}


# --- Button Classes for Quiz Interaction ---

class QuizAnswerButton(discord.ui.Button):
    """Button for answering a quiz question."""
    
    def __init__(self, question_idx: int, choice: str, label: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=f"{choice}",
            custom_id=f"quiz_{question_idx}_{choice}"
        )
        self.question_idx = question_idx
        self.choice = choice
    
    async def callback(self, interaction: discord.Interaction):
        """Handle button click."""
        quiz_logger.info(f"Button click: user={interaction.user.name}({interaction.user.id}) guild={interaction.guild.name if interaction.guild else 'DM'}({interaction.guild_id if interaction.guild else 'N/A'}) channel={interaction.channel_id} question={self.question_idx+1} choice={self.choice}")
        
        state = QUIZ_STATE.get(interaction.channel_id)
        if not state:
            quiz_logger.warning(f"No quiz running in channel {interaction.channel_id} for user {interaction.user.name}({interaction.user.id})")
            await interaction.response.send_message(
                "❌ No quiz is running in this channel.",
                ephemeral=True
            )
            return
        
        # Check if quiz has ended
        if datetime.utcnow() >= state["end_time"]:
            quiz_logger.warning(f"User {interaction.user.name}({interaction.user.id}) attempted to answer after quiz ended in channel {interaction.channel_id}")
            await interaction.response.send_message(
                "❌ This quiz has ended! Results are being calculated.",
                ephemeral=True
            )
            return
        
        # Validate question number
        if self.question_idx < 0 or self.question_idx >= len(state["questions"]):
            quiz_logger.error(f"Invalid question index {self.question_idx} for user {interaction.user.name}({interaction.user.id}) in channel {interaction.channel_id}")
            await interaction.response.send_message(
                f"❌ Invalid question.",
                ephemeral=True
            )
            return
        
        user_id = str(interaction.user.id)
        
        # Initialize user's answers if needed
        if user_id not in state["user_answers"]:
            state["user_answers"][user_id] = {}
            quiz_logger.debug(f"Initialized answer dict for user {interaction.user.name}({user_id}) in channel {interaction.channel_id}")
        
        # Store the answer
        state["user_answers"][user_id][self.question_idx] = self.choice
        quiz_logger.info(f"Stored answer: user={interaction.user.name}({user_id}) channel={interaction.channel_id} q={self.question_idx+1} answer={self.choice}")
        
        # Calculate how many questions they've answered
        answered_count = len(state["user_answers"][user_id])
        total_questions = len(state["questions"])
        
        time_remaining = state["end_time"] - datetime.utcnow()
        minutes_remaining = int(time_remaining.total_seconds() / 60)
        seconds_remaining = int(time_remaining.total_seconds() % 60)
        
        quiz_logger.debug(f"User {interaction.user.name}({user_id}) progress: {answered_count}/{total_questions} answered, {minutes_remaining}m {seconds_remaining}s remaining")
        
        await interaction.response.send_message(
            f"📝 Answer **{self.choice}** recorded for question {self.question_idx + 1}!\n"
            f"📊 You've answered {answered_count}/{total_questions} questions.\n"
            f"⏱️ Time remaining: {minutes_remaining}m {seconds_remaining}s",
            ephemeral=True
        )


class QuizQuestionView(discord.ui.View):
    """View containing buttons for a quiz question."""
    
    def __init__(self, question_idx: int, options: List[str]):
        super().__init__(timeout=None)  # No timeout since quiz has its own timer
        
        # Add buttons for each option (A, B, C, D)
        choices = ["A", "B", "C", "D"]
        for i, (choice, option_text) in enumerate(zip(choices[:len(options)], options)):
            button = QuizAnswerButton(question_idx, choice, option_text)
            self.add_item(button)


# --- Helper Functions ---

async def check_bot_permissions(interaction: discord.Interaction) -> Tuple[bool, Optional[str]]:
    """
    Check if the bot has required permissions in the current channel.
    Returns (has_permissions, error_message).
    
    Required permissions:
    - Send Messages
    - Embed Links
    - Read Message History
    - View Channel
    """
    if not interaction.guild:
        # DM channels - bot always has permissions
        return True, None
    
    channel = interaction.channel
    bot_member = interaction.guild.get_member(client.user.id)
    
    if not bot_member:
        return False, "❌ Bot member not found in guild."
    
    # Get bot's effective permissions in the channel
    bot_perms = channel.permissions_for(bot_member)
    
    # Define required permissions
    required_perms = {
        "send_messages": "Send Messages",
        "embed_links": "Embed Links",
        "read_message_history": "Read Message History",
        "view_channel": "View Channel"
    }
    
    # Check which permissions are missing
    missing_perms = []
    for perm_attr, perm_name in required_perms.items():
        if not getattr(bot_perms, perm_attr, False):
            missing_perms.append(perm_name)
    
    if not missing_perms:
        return True, None
    
    # Permissions are missing - identify the cause
    error_parts = [f"❌ **Missing Permissions in this channel:**"]
    error_parts.append(f"Missing: {', '.join(f'**{p}**' for p in missing_perms)}")
    error_parts.append("")
    error_parts.append("**Cause Analysis:**")
    
    # Check channel overwrites to find blockers
    blockers = []
    
    # Check @everyone overwrite
    everyone_overwrite = channel.overwrites_for(interaction.guild.default_role)
    for perm_attr, perm_name in required_perms.items():
        perm_value = getattr(everyone_overwrite, perm_attr, None)
        if perm_value is False:  # Explicitly denied
            blockers.append(f"• @everyone role explicitly **denies** `{perm_name}`")
    
    # Check bot's role overwrites
    for role in bot_member.roles:
        if role == interaction.guild.default_role:
            continue
        role_overwrite = channel.overwrites_for(role)
        for perm_attr, perm_name in required_perms.items():
            perm_value = getattr(role_overwrite, perm_attr, None)
            if perm_value is False:  # Explicitly denied
                blockers.append(f"• Role {role.mention} explicitly **denies** `{perm_name}`")
    
    # Check member-specific overwrite (rare but possible)
    member_overwrite = channel.overwrites_for(bot_member)
    for perm_attr, perm_name in required_perms.items():
        perm_value = getattr(member_overwrite, perm_attr, None)
        if perm_value is False:  # Explicitly denied
            blockers.append(f"• Bot member override explicitly **denies** `{perm_name}`")
    
    if blockers:
        error_parts.extend(blockers)
    else:
        # No explicit denies found - must be missing from base roles
        error_parts.append(f"• The bot's roles don't grant these permissions globally")
        error_parts.append(f"• No channel overwrites are blocking (but none are allowing either)")
    
    error_parts.append("")
    error_parts.append("**How to fix:**")
    error_parts.append("1. Check channel permission overwrites for roles/members")
    error_parts.append("2. Grant the bot's role the required permissions server-wide, OR")
    error_parts.append("3. Add channel-specific permission overwrites to allow the bot")
    
    return False, "\n".join(error_parts)

async def ask_assistant(user_msg: str, guild_id: Optional[int] = None, timeout: int = 30, temperature: float = None) -> str:
    """
    Ask the OpenAI Assistant a question using Assistants API v2.
    Uses File Search to ground responses in the uploaded PDF.
    
    Args:
        user_msg: The message/prompt to send to the assistant
        guild_id: The guild ID to use for getting the appropriate OpenAI client and assistant
        timeout: Maximum seconds to wait for response
        temperature: Optional temperature for response generation (0.0-2.0)
    """
    api_logger.debug(f"ask_assistant called: msg_len={len(user_msg)} guild_id={guild_id} timeout={timeout} temperature={temperature}")
    
    # Get guild-specific OpenAI client and assistant ID
    oai = get_openai_client(guild_id)
    if not oai:
        return "❌ This server hasn't been configured yet. An admin needs to run `/setup` first."
    
    assistant_id = get_assistant_id(guild_id)
    if not assistant_id:
        return "❌ No assistant configured for this server. An admin needs to run `/setup` first."
    
    try:
        # Create a new thread for this question
        thread = oai.beta.threads.create()
        api_logger.debug(f"Created thread: {thread.id}")
        
        # Add user message to thread
        oai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_msg
        )
        api_logger.debug(f"Added message to thread {thread.id}")
        
        # Build run parameters
        run_params = {
            "thread_id": thread.id,
            "assistant_id": assistant_id
        }
        
        # Add optional parameters if provided
        if temperature is not None:
            run_params["temperature"] = temperature
        
        # Create and run the assistant (v2 API)
        run = oai.beta.threads.runs.create(**run_params)
        api_logger.debug(f"Created run: {run.id} for thread {thread.id}")
        
        # Poll until complete (with timeout)
        elapsed = 0
        while elapsed < timeout:
            run = oai.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )
            
            if run.status in ("completed", "failed", "cancelled", "expired"):
                break
                
            await asyncio.sleep(0.7)
            elapsed += 0.7
        
        api_logger.info(f"Run completed: status={run.status} elapsed={elapsed:.1f}s thread={thread.id}")
        
        if run.status != "completed":
            api_logger.warning(f"Assistant didn't respond in time: status={run.status} thread={thread.id}")
            return f"⚠️ Assistant didn't respond in time (status: {run.status}). Try again."
        
        # Retrieve messages
        messages = oai.beta.threads.messages.list(thread_id=thread.id)
        
        # Find the latest assistant message
        for msg in messages.data:
            if msg.role == "assistant":
                chunks = []
                for content in msg.content:
                    if content.type == "text":
                        text = content.text.value
                        # Remove citation markers like 【4:2†source】
                        text = re.sub(r'【[^】]*】', '', text)
                        chunks.append(text)
                
                response = "\n".join(chunks) if chunks else "No response from assistant."
                api_logger.info(f"Assistant response received: length={len(response)} thread={thread.id}")
                return response
        
        api_logger.warning(f"No assistant message found in thread {thread.id}")
        return "No response from assistant."
        
    except Exception as e:
        api_logger.error(f"Error asking assistant: {e}", exc_info=True)
        return f"❌ Error communicating with AI: {str(e)}"


def format_mcq(question: str, options: List[str], question_num: int = None, total: int = None) -> discord.Embed:
    """Format a multiple choice question as a Discord embed with forest green border."""
    letters = ["A", "B", "C", "D", "E", "F"][:len(options)]
    
    # Clean options to remove any leading letter prefixes
    cleaned_options = []
    for opt in options:
        # Strip leading whitespace
        cleaned = opt.strip()
        # Remove leading letter prefix patterns: "A)", "A.", "A:", "A -", etc.
        if len(cleaned) >= 2 and cleaned[0].upper() in 'ABCDEF':
            second_char = cleaned[1]
            # Check for common separators after the letter
            if second_char in ').:- ':
                # Find where the actual text starts (skip past separator and whitespace)
                start_idx = 2
                while start_idx < len(cleaned) and cleaned[start_idx] in ' \t':
                    start_idx += 1
                cleaned = cleaned[start_idx:]
        cleaned_options.append(cleaned)
    
    # Forest green color similar to flight suit (hex #2d5016)
    embed = discord.Embed(
        color=0x2d5016
    )
    
    # Add question number as non-bold text if provided
    if question_num is not None and total is not None:
        embed.description = f"Question {question_num}/{total}\n\n**{question}**"
    else:
        embed.description = f"**{question}**"
    
    # Add options as a field
    options_text = "\n".join(f"**{letter})** {opt}" for letter, opt in zip(letters, cleaned_options))
    embed.add_field(name="\u200b", value=options_text, inline=False)
    
    return embed


def shuffle_quiz_options(question: dict) -> dict:
    """
    Shuffle the options in a quiz question and update the correct answer letter.
    Returns a new dict with shuffled options and updated answer.
    """
    # Get the original correct answer index (A=0, B=1, C=2, D=3)
    answer_letter = question["answer"].strip().upper()
    answer_index = ord(answer_letter) - ord('A')
    
    # Create a list of (option_text, is_correct) tuples
    options_with_correctness = [
        (opt, i == answer_index) 
        for i, opt in enumerate(question["options"])
    ]
    
    # Shuffle the options
    random.shuffle(options_with_correctness)
    
    # Find the new position of the correct answer
    new_answer_index = next(
        i for i, (_, is_correct) in enumerate(options_with_correctness) 
        if is_correct
    )
    
    # Create the shuffled question, preserving optional fields
    shuffled_question = {
        "q": question["q"],
        "options": [opt for opt, _ in options_with_correctness],
        "answer": chr(ord('A') + new_answer_index),
        "explain": question["explain"]
    }
    
    # Preserve optional topic and page fields if present
    if "topic" in question:
        shuffled_question["topic"] = question["topic"]
    if "page" in question:
        shuffled_question["page"] = question["page"]
    
    return shuffled_question


# --- Deduplication Helper Functions ---

STOPWORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'should', 'could', 'may', 'might', 'must', 'can', 'what', 'which',
    'who', 'when', 'where', 'why', 'how', 'this', 'that', 'these', 'those'
}


def extract_topic_from_question(question_dict: dict) -> str:
    """
    Extract or compute a topic tag for a question.
    Uses the 'topic' field if present, otherwise extracts from question text.
    
    Args:
        question_dict: Question dictionary with 'q' and optionally 'topic' fields
    
    Returns:
        A normalized topic string (lowercase, hyphenated)
    """
    # Use provided topic if available
    if "topic" in question_dict and question_dict["topic"]:
        return question_dict["topic"].lower().strip()
    
    # Extract from question text
    question_text = question_dict.get("q", "").lower()
    
    # Remove punctuation and split into words
    words = re.findall(r'\b[a-z]+\b', question_text)
    
    # Filter out stopwords and short words
    content_words = [w for w in words if w not in STOPWORDS and len(w) > 3]
    
    # Count word frequencies
    if not content_words:
        return "unknown"
    
    word_counts = Counter(content_words)
    
    # Take top 2-3 most common words
    top_words = [word for word, _ in word_counts.most_common(3)]
    
    # Create hyphenated topic tag
    topic = "-".join(top_words[:2]) if len(top_words) >= 2 else (top_words[0] if top_words else "unknown")
    
    return topic


def extract_keywords(text: str, top_n: int = 5) -> Set[str]:
    """
    Extract top N keywords from text (after removing stopwords).
    
    Args:
        text: Input text
        top_n: Number of top keywords to extract
    
    Returns:
        Set of top keywords
    """
    text = text.lower()
    words = re.findall(r'\b[a-z]+\b', text)
    content_words = [w for w in words if w not in STOPWORDS and len(w) > 3]
    
    if not content_words:
        return set()
    
    word_counts = Counter(content_words)
    return set(word for word, _ in word_counts.most_common(top_n))


def are_questions_similar(q1: dict, q2: dict, topic1: str, topic2: str) -> bool:
    """
    Determine if two questions are too similar and should be considered duplicates.
    
    Considers questions duplicates if:
    - Topics match exactly
    - Question text similarity > 85% (fuzzy ratio)
    - Share > 40% of top 5 keywords
    
    Args:
        q1, q2: Question dictionaries
        topic1, topic2: Topic tags for the questions
    
    Returns:
        True if questions are too similar
    """
    # Check exact topic match
    if topic1 == topic2:
        return True
    
    # Check fuzzy text similarity
    text1 = q1.get("q", "")
    text2 = q2.get("q", "")
    
    if fuzz.ratio(text1.lower(), text2.lower()) > 85:
        return True
    
    # Check keyword overlap
    keywords1 = extract_keywords(text1)
    keywords2 = extract_keywords(text2)
    
    if keywords1 and keywords2:
        overlap = len(keywords1 & keywords2)
        total = len(keywords1 | keywords2)
        if total > 0 and overlap / total > 0.4:
            return True
    
    return False


def deduplicate_questions(questions: List[dict]) -> Tuple[List[dict], List[str]]:
    """
    Remove duplicate/similar questions from a list.
    
    Args:
        questions: List of question dictionaries
    
    Returns:
        Tuple of (unique_questions, used_topics)
    """
    unique = []
    topics = []
    
    for q in questions:
        topic = extract_topic_from_question(q)
        
        # Check if this question is similar to any already in unique list
        is_duplicate = False
        for existing_q, existing_topic in zip(unique, topics):
            if are_questions_similar(q, existing_q, topic, existing_topic):
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique.append(q)
            topics.append(topic)
    
    return unique, topics


async def generate_quiz(topic_hint: str = "", num_questions: int = 6, guild_id: Optional[int] = None) -> Optional[List[dict]]:
    """
    Generate a quiz from the PDF using the Assistant.
    Enforces diversity by deduplicating questions and regenerating if needed.
    Returns a list of question dicts or None on failure.
    
    Args:
        topic_hint: Optional topic to focus on
        num_questions: Number of questions to generate
        guild_id: Guild ID for getting the appropriate OpenAI client
    """
    max_regeneration_attempts = 3
    unique_questions = []
    used_topics = []
    
    # Initial prompt with diversity requirements
    prompt = f"""Generate {num_questions} multiple-choice questions based ONLY on the attached PDF.

Requirements:
- Each question must have exactly 4 options
- Include the correct answer (A, B, C, or D)
- Provide a brief explanation with page number citation
- Focus on practical knowledge for DCS pilots
- Ensure every question covers a different topic or concept from the PDF and avoid repeating the same keywords across multiple questions (for example, do NOT repeat 'PUSHING' or 'FUMBLE')

{f'Topic focus: {topic_hint}' if topic_hint else 'Cover various topics from the document.'}

Return ONLY a valid JSON array with this exact structure:
[
  {{
    "q": "Question text here?",
    "options": ["Option A text", "Option B text", "Option C text", "Option D text"],
    "answer": "A",
    "explain": "Brief explanation with page reference (p.XX)",
    "page": 12,
    "topic": "engine-trim"
  }}
]

Each question MUST include:
- "topic": A short hyphenated tag or 2-3 word phrase identifying the concept (e.g., "fuel-system", "emergency-procedures", "engine-trim")
- "page": The page number from the PDF where this information is found

If you cannot generate {num_questions} distinct topics, return fewer items with a "note" field explaining why.

IMPORTANT: Return ONLY the JSON array, no other text."""

    # Call assistant with diversity parameters
    api_logger.info(f"Generating quiz: topic_hint='{topic_hint}', num_questions={num_questions}, guild_id={guild_id}")
    reply = await ask_assistant(prompt, guild_id=guild_id, timeout=45, temperature=0.7)
    
    # Log the raw assistant reply
    api_logger.debug(f"Assistant raw reply (first 1000 chars): {reply[:1000]}")
    
    try:
        # Try to extract JSON from the response
        reply_clean = reply.strip()
        if reply_clean.startswith("```json"):
            reply_clean = reply_clean[7:]
        if reply_clean.startswith("```"):
            reply_clean = reply_clean[3:]
        if reply_clean.endswith("```"):
            reply_clean = reply_clean[:-3]
        
        reply_clean = reply_clean.strip()
        
        data = json.loads(reply_clean)
        
        # Validate questions
        valid_questions = []
        for item in data:
            if all(k in item for k in ("q", "options", "answer", "explain")):
                if len(item["options"]) == 4:
                    item["answer"] = item["answer"].strip().upper()
                    if item["answer"] in ["A", "B", "C", "D"]:
                        valid_questions.append(item)
        
        if not valid_questions:
            api_logger.warning("No valid questions returned from assistant")
            return None
        
        # Deduplicate initial set
        unique_questions, used_topics = deduplicate_questions(valid_questions)
        api_logger.info(f"After deduplication: {len(unique_questions)} unique out of {len(valid_questions)} initial questions")
        api_logger.info(f"Used topics: {used_topics}")
        
        # Regeneration loop if we don't have enough unique questions
        attempt = 0
        while len(unique_questions) < num_questions and attempt < max_regeneration_attempts:
            attempt += 1
            needed = num_questions - len(unique_questions)
            
            api_logger.info(f"Regeneration attempt {attempt}/{max_regeneration_attempts}: need {needed} more questions")
            
            # Build regeneration prompt with excluded topics
            regen_prompt = f"""Generate {needed + 2} additional multiple-choice questions based ONLY on the attached PDF.

IMPORTANT: Do NOT generate questions about these topics (already covered): {', '.join(used_topics)}

Requirements:
- Each question must have exactly 4 options
- Include the correct answer (A, B, C, or D)
- Provide a brief explanation with page number citation
- Focus on practical knowledge for DCS pilots
- Each question MUST cover a DIFFERENT topic from those listed above
- Ensure every question has a unique topic tag

{f'Topic focus: {topic_hint}' if topic_hint else 'Cover various topics from the document.'}

Return ONLY a valid JSON array with this exact structure:
[
  {{
    "q": "Question text here?",
    "options": ["Option A text", "Option B text", "Option C text", "Option D text"],
    "answer": "A",
    "explain": "Brief explanation with page reference (p.XX)",
    "page": 12,
    "topic": "unique-topic-tag"
  }}
]

Each question MUST include a unique "topic" tag (different from: {', '.join(used_topics)}).

IMPORTANT: Return ONLY the JSON array, no other text."""
            
            regen_reply = await ask_assistant(regen_prompt, guild_id=guild_id, timeout=45, temperature=0.8)
            api_logger.debug(f"Regeneration reply (first 500 chars): {regen_reply[:500]}")
            
            try:
                # Parse regenerated questions
                regen_clean = regen_reply.strip()
                if regen_clean.startswith("```json"):
                    regen_clean = regen_clean[7:]
                if regen_clean.startswith("```"):
                    regen_clean = regen_clean[3:]
                if regen_clean.endswith("```"):
                    regen_clean = regen_clean[:-3]
                
                regen_clean = regen_clean.strip()
                regen_data = json.loads(regen_clean)
                
                # Validate regenerated questions
                regen_valid = []
                for item in regen_data:
                    if all(k in item for k in ("q", "options", "answer", "explain")):
                        if len(item["options"]) == 4:
                            item["answer"] = item["answer"].strip().upper()
                            if item["answer"] in ["A", "B", "C", "D"]:
                                regen_valid.append(item)
                
                # Add non-duplicate questions
                for q in regen_valid:
                    topic = extract_topic_from_question(q)
                    
                    # Check if similar to existing questions
                    is_duplicate = False
                    for existing_q, existing_topic in zip(unique_questions, used_topics):
                        if are_questions_similar(q, existing_q, topic, existing_topic):
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        unique_questions.append(q)
                        used_topics.append(topic)
                        api_logger.debug(f"Added new unique question with topic: {topic}")
                        
                        # Stop if we have enough
                        if len(unique_questions) >= num_questions:
                            break
                
            except (json.JSONDecodeError, Exception) as e:
                api_logger.error(f"Error parsing regeneration attempt {attempt}: {e}")
                continue
        
        # Log final results
        final_count = len(unique_questions)
        api_logger.info(f"Final quiz: {final_count} unique questions (requested: {num_questions})")
        api_logger.info(f"Final topics: {used_topics}")
        
        # Return the requested number or what we have
        if final_count >= num_questions:
            result = unique_questions[:num_questions]
            api_logger.info(f"Returning {len(result)} questions")
            return result
        elif final_count > 0:
            # Return what we have with a note
            api_logger.warning(f"Could only generate {final_count} unique questions (requested {num_questions})")
            return unique_questions
        else:
            api_logger.error("Failed to generate any unique questions")
            return None
        
    except json.JSONDecodeError as e:
        api_logger.error(f"JSON parse error: {e}")
        api_logger.error(f"Response was: {reply[:500]}")
        return None
    except Exception as e:
        api_logger.error(f"Quiz generation error: {e}")
        return None


async def auto_end_quiz(channel_id: int, channel, duration_minutes: int):
    """Automatically end the quiz after the specified duration."""
    quiz_logger.info(f"Auto-end task started for channel {channel_id}, will end in {duration_minutes} minutes")
    
    try:
        await asyncio.sleep(duration_minutes * 60)
        
        # Check if quiz still exists
        state = QUIZ_STATE.get(channel_id)
        if not state:
            quiz_logger.warning(f"Auto-end: quiz no longer exists in channel {channel_id}")
            return
        
        quiz_logger.info(f"Auto-ending quiz in channel {channel_id} after {duration_minutes} minutes")
        
        # Calculate and display results
        await display_quiz_results(channel, channel_id)
        
    except Exception as e:
        quiz_logger.error(f"Error in auto_end_quiz for channel {channel_id}: {e}", exc_info=True)


async def display_quiz_results(channel, channel_id: int):
    """Display quiz results and clean up state."""
    quiz_logger.info(f"Displaying quiz results for channel {channel_id}")
    
    state = QUIZ_STATE.get(channel_id)
    if not state:
        quiz_logger.warning(f"No quiz state found for channel {channel_id}")
        return
    
    questions = state["questions"]
    user_answers = state["user_answers"]
    
    quiz_logger.info(f"Quiz results: {len(questions)} questions, {len(user_answers)} users participated")
    quiz_logger.debug(f"User answers data: {user_answers}")
    
    # Calculate scores
    scores = {}
    for user_id, answers in user_answers.items():
        score = 0
        for q_idx, choice in answers.items():
            if q_idx < len(questions):
                correct_answer = questions[q_idx]["answer"].strip().upper()
                if choice == correct_answer:
                    score += 1
        scores[user_id] = score
        quiz_logger.debug(f"User {user_id} score: {score}/{len(questions)}")
    
    # Sort by score
    scores_sorted = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    total_questions = len(questions)
    
    # Forest green color for embeds
    embed_color = 0x2d5016
    
    # Create leaderboard embed
    leaderboard_embed = discord.Embed(
        title="🏁 Quiz Complete!",
        color=embed_color
    )
    
    if scores_sorted:
        leaderboard_text = "\n".join(
            f"{'🥇' if i == 0 else '🥈' if i == 1 else '🥉' if i == 2 else '📊'} <@{uid}>: **{score}/{total_questions}** ({int(score/total_questions*100)}%)"
            for i, (uid, score) in enumerate(scores_sorted)
        )
        leaderboard_embed.add_field(name="Final Scores", value=leaderboard_text, inline=False)
        quiz_logger.info(f"Leaderboard: {[(uid, score) for uid, score in scores_sorted]}")
    else:
        leaderboard_embed.description = "No one submitted answers!"
        quiz_logger.info("No participants submitted answers")
    
    await channel.send(embed=leaderboard_embed)
    quiz_logger.info(f"Sent leaderboard embed to channel {channel_id}")
    
    # Create detailed results for each question
    for idx, q in enumerate(questions):
        quiz_logger.debug(f"Processing results for question {idx+1}/{total_questions}")
        
        result_embed = discord.Embed(
            title=f"Question {idx+1}/{total_questions}",
            description=f"**{q['q']}**",
            color=embed_color
        )
        
        # Show the correct answer
        result_embed.add_field(
            name="✅ Correct Answer",
            value=f"**{q['answer']}**",
            inline=False
        )
        
        # Collect users who answered correctly
        correct_users = []
        incorrect_users = []
        for user_id, answers in user_answers.items():
            if idx in answers:
                if answers[idx] == q["answer"].strip().upper():
                    correct_users.append(user_id)
                else:
                    incorrect_users.append(user_id)
        
        quiz_logger.info(f"Question {idx+1} results: {len(correct_users)} correct, {len(incorrect_users)} incorrect")
        quiz_logger.debug(f"Question {idx+1} correct users: {correct_users}")
        quiz_logger.debug(f"Question {idx+1} incorrect users: {incorrect_users}")
        
        # Show who answered correctly
        if correct_users:
            correct_mentions = ", ".join(f"<@{uid}>" for uid in correct_users)
            quiz_logger.debug(f"Question {idx+1} correct mentions string (len={len(correct_mentions)}): {correct_mentions}")
            result_embed.add_field(
                name="✅ Answered Correctly",
                value=correct_mentions,
                inline=False
            )
        
        # Show who answered incorrectly
        if incorrect_users:
            incorrect_mentions = ", ".join(f"<@{uid}>" for uid in incorrect_users)
            quiz_logger.debug(f"Question {idx+1} incorrect mentions string (len={len(incorrect_mentions)}): {incorrect_mentions}")
            result_embed.add_field(
                name="❌ Answered Incorrectly",
                value=incorrect_mentions,
                inline=False
            )
        
        # Show explanation
        result_embed.add_field(
            name="📖 Explanation",
            value=q['explain'],
            inline=False
        )
        
        await channel.send(embed=result_embed)
        quiz_logger.debug(f"Sent results embed for question {idx+1} to channel {channel_id}")
    
    # Send closing message
    await channel.send("Start a new quiz with `/quiz_start`!")
    
    # Clean up state
    QUIZ_STATE.pop(channel_id, None)
    quiz_logger.info(f"Cleaned up quiz state for channel {channel_id}")


# --- Discord Commands ---

@tree.command(name="ask", description="Ask a question about the SOP documentation")
async def ask_command(interaction: discord.Interaction, question: str):
    """Ask the bot a question grounded in the uploaded PDF."""
    discord_logger.info(f"/ask command: user={interaction.user.name}({interaction.user.id}) guild={interaction.guild.name if interaction.guild else 'DM'}({interaction.guild_id if interaction.guild else 'N/A'}) channel={interaction.channel_id} question='{question[:100]}'")
    
    # Check permissions first
    has_perms, perm_error = await check_bot_permissions(interaction)
    if not has_perms:
        discord_logger.warning(f"/ask permission denied for user {interaction.user.name}({interaction.user.id}) in channel {interaction.channel_id}")
        await interaction.response.send_message(perm_error, ephemeral=True)
        return
    
    await interaction.response.defer(thinking=True)
    
    enhanced_question = f"{question}\n\n(Answer using ONLY information from the attached PDF documentation. Include page numbers when possible. If the answer isn't in the PDF, say so clearly. Your response MUST be less than 2000 characters to fit in a Discord message.)"
    
    api_logger.debug(f"Sending question to assistant API: '{enhanced_question[:100]}'")
    answer = await ask_assistant(enhanced_question, guild_id=interaction.guild_id)
    api_logger.debug(f"Received answer from assistant API (length={len(answer)})")
    
    # Discord has a 2000 character limit
    if len(answer) > 1998:
        answer = answer[:1997] + "..."
        api_logger.warning(f"Answer truncated to 1998 characters")
    
    await interaction.followup.send(answer)
    discord_logger.info(f"/ask completed for user {interaction.user.name}({interaction.user.id})")


@tree.command(name="quiz_start", description="Start a quiz from the SOP documentation")
async def quiz_start(interaction: discord.Interaction, topic: str = "", questions: int = 6, duration: int = 5):
    """Start a new quiz session in this channel."""
    discord_logger.info(f"/quiz_start command: user={interaction.user.name}({interaction.user.id}) guild={interaction.guild.name if interaction.guild else 'DM'}({interaction.guild_id if interaction.guild else 'N/A'}) channel={interaction.channel_id} topic='{topic}' questions={questions} duration={duration}")
    
    # Check permissions first
    has_perms, perm_error = await check_bot_permissions(interaction)
    if not has_perms:
        discord_logger.warning(f"/quiz_start permission denied for user {interaction.user.name}({interaction.user.id}) in channel {interaction.channel_id}")
        await interaction.response.send_message(perm_error, ephemeral=True)
        return
    
    if questions < 1 or questions > 10:
        discord_logger.warning(f"/quiz_start invalid question count {questions} from user {interaction.user.name}({interaction.user.id})")
        await interaction.response.send_message(
            "❌ Please choose between 1 and 10 questions.",
            ephemeral=True
        )
        return
    
    if duration < 1 or duration > 60:
        discord_logger.warning(f"/quiz_start invalid duration {duration} from user {interaction.user.name}({interaction.user.id})")
        await interaction.response.send_message(
            "❌ Please choose a duration between 1 and 60 minutes.",
            ephemeral=True
        )
        return
    
    if interaction.channel_id in QUIZ_STATE:
        discord_logger.warning(f"/quiz_start attempted but quiz already running in channel {interaction.channel_id}")
        await interaction.response.send_message(
            "⚠️ There's already a quiz running in this channel! Finish it first or use `/quiz_end` to cancel.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(thinking=True)
    
    quiz_logger.info(f"Generating quiz: topic='{topic}' questions={questions} duration={duration} for channel {interaction.channel_id}")
    quiz_questions = await generate_quiz(topic_hint=topic, num_questions=questions, guild_id=interaction.guild_id)
    
    if not quiz_questions:
        quiz_logger.error(f"Failed to generate quiz for channel {interaction.channel_id}")
        await interaction.followup.send(
            "❌ Couldn't generate a quiz right now. Try:\n"
            "• A more specific topic\n"
            "• Fewer questions\n"
            "• Asking again in a moment"
        )
        return
    
    # Shuffle the options for each question to randomize correct answer position
    shuffled_questions = [shuffle_quiz_options(q) for q in quiz_questions]
    
    end_time = datetime.utcnow() + timedelta(minutes=duration)
    
    QUIZ_STATE[interaction.channel_id] = {
        "questions": shuffled_questions,
        "user_answers": {},  # {user_id: {question_idx: choice}}
        "end_time": end_time,
        "duration_minutes": duration,
        "initiator": interaction.user.id
    }
    
    quiz_logger.info(f"Quiz started in channel {interaction.channel_id} by user {interaction.user.name}({interaction.user.id}): {len(shuffled_questions)} questions, {duration} minutes")
    
    topic_text = f" (Topic: {topic})" if topic else ""
    
    # Schedule auto-end task
    asyncio.create_task(auto_end_quiz(interaction.channel_id, interaction.channel, duration))
    
    # Send initial message with embed
    start_embed = discord.Embed(
        title="✈️ Quiz Started!",
        description=f"{topic_text if topic else ''}",
        color=0x2d5016
    )
    start_embed.add_field(
        name="⏱️ Duration",
        value=f"**{duration} minute(s)**",
        inline=True
    )
    start_embed.add_field(
        name="📝 Questions",
        value=f"**{len(shuffled_questions)}**",
        inline=True
    )
    start_embed.add_field(
        name="Instructions",
        value="Click the buttons below each question to answer!\nResults will be revealed when the timer ends!",
        inline=False
    )
    
    await interaction.followup.send(embed=start_embed)
    
    # Send each question with its button options
    for idx, q in enumerate(shuffled_questions):
        question_embed = format_mcq(q["q"], q["options"], idx + 1, len(shuffled_questions))
        view = QuizQuestionView(idx, q["options"])
        await interaction.channel.send(embed=question_embed, view=view)
    
    quiz_logger.info(f"All quiz questions posted to channel {interaction.channel_id}")


@tree.command(name="quiz_answer", description="Answer a quiz question (alternative to buttons)")
async def quiz_answer(interaction: discord.Interaction, question_number: int, choice: str):
    """Submit an answer to a quiz question."""
    discord_logger.info(f"/quiz_answer command: user={interaction.user.name}({interaction.user.id}) guild={interaction.guild.name if interaction.guild else 'DM'}({interaction.guild_id if interaction.guild else 'N/A'}) channel={interaction.channel_id} q={question_number} choice={choice}")
    
    choice = choice.strip().upper()
    
    if choice not in ["A", "B", "C", "D"]:
        discord_logger.warning(f"/quiz_answer invalid choice '{choice}' from user {interaction.user.name}({interaction.user.id})")
        await interaction.response.send_message(
            "❌ Please answer with A, B, C, or D.",
            ephemeral=True
        )
        return
    
    state = QUIZ_STATE.get(interaction.channel_id)
    if not state:
        discord_logger.warning(f"/quiz_answer no quiz in channel {interaction.channel_id} for user {interaction.user.name}({interaction.user.id})")
        await interaction.response.send_message(
            "❌ No quiz is running in this channel. Use `/quiz_start` to begin!",
            ephemeral=True
        )
        return
    
    # Check if quiz has ended
    if datetime.utcnow() >= state["end_time"]:
        discord_logger.warning(f"/quiz_answer after quiz ended in channel {interaction.channel_id} for user {interaction.user.name}({interaction.user.id})")
        await interaction.response.send_message(
            "❌ This quiz has ended! Results are being calculated.",
            ephemeral=True
        )
        return
    
    # Validate question number
    question_idx = question_number - 1
    if question_idx < 0 or question_idx >= len(state["questions"]):
        discord_logger.error(f"/quiz_answer invalid question number {question_number} from user {interaction.user.name}({interaction.user.id}) in channel {interaction.channel_id}")
        await interaction.response.send_message(
            f"❌ Invalid question number. Please choose between 1 and {len(state['questions'])}.",
            ephemeral=True
        )
        return
    
    user_id = str(interaction.user.id)
    
    # Initialize user's answers if needed
    if user_id not in state["user_answers"]:
        state["user_answers"][user_id] = {}
        quiz_logger.debug(f"Initialized answer dict for user {interaction.user.name}({user_id}) in channel {interaction.channel_id}")
    
    # Store the answer
    state["user_answers"][user_id][question_idx] = choice
    quiz_logger.info(f"Stored answer via command: user={interaction.user.name}({user_id}) channel={interaction.channel_id} q={question_number} answer={choice}")
    
    # Calculate how many questions they've answered
    answered_count = len(state["user_answers"][user_id])
    total_questions = len(state["questions"])
    
    time_remaining = state["end_time"] - datetime.utcnow()
    minutes_remaining = int(time_remaining.total_seconds() / 60)
    seconds_remaining = int(time_remaining.total_seconds() % 60)
    
    quiz_logger.debug(f"User {interaction.user.name}({user_id}) progress: {answered_count}/{total_questions} answered, {minutes_remaining}m {seconds_remaining}s remaining")
    
    await interaction.response.send_message(
        f"📝 Answer recorded for question {question_number}!\n"
        f"📊 You've answered {answered_count}/{total_questions} questions.\n"
        f"⏱️ Time remaining: {minutes_remaining}m {seconds_remaining}s",
        ephemeral=True
    )


@tree.command(name="quiz_end", description="End the current quiz and show results")
async def quiz_end(interaction: discord.Interaction):
    """End the current quiz and display results."""
    discord_logger.info(f"/quiz_end command: user={interaction.user.name}({interaction.user.id}) guild={interaction.guild.name if interaction.guild else 'DM'}({interaction.guild_id if interaction.guild else 'N/A'}) channel={interaction.channel_id}")
    
    # Check permissions first
    has_perms, perm_error = await check_bot_permissions(interaction)
    if not has_perms:
        discord_logger.warning(f"/quiz_end permission denied for user {interaction.user.name}({interaction.user.id}) in channel {interaction.channel_id}")
        await interaction.response.send_message(perm_error, ephemeral=True)
        return
    
    if interaction.channel_id not in QUIZ_STATE:
        discord_logger.warning(f"/quiz_end no quiz in channel {interaction.channel_id}")
        await interaction.response.send_message(
            "❌ No quiz is running in this channel.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer()
    
    quiz_logger.info(f"Quiz manually ended in channel {interaction.channel_id} by user {interaction.user.name}({interaction.user.id})")
    
    # Display results
    await display_quiz_results(interaction.channel, interaction.channel_id)
    
    await interaction.followup.send("🛑 Quiz ended by moderator.")


@tree.command(name="quiz_score", description="Check your quiz progress")
async def quiz_score(interaction: discord.Interaction):
    """Show your current quiz progress."""
    discord_logger.debug(f"/quiz_score command: user={interaction.user.name}({interaction.user.id}) guild={interaction.guild.name if interaction.guild else 'DM'}({interaction.guild_id if interaction.guild else 'N/A'}) channel={interaction.channel_id}")
    
    state = QUIZ_STATE.get(interaction.channel_id)
    if not state:
        await interaction.response.send_message(
            "❌ No quiz is running in this channel.",
            ephemeral=True
        )
        return
    
    user_id = str(interaction.user.id)
    total_q = len(state["questions"])
    
    if user_id not in state["user_answers"]:
        answered_count = 0
    else:
        answered_count = len(state["user_answers"][user_id])
    
    time_remaining = state["end_time"] - datetime.utcnow()
    minutes_remaining = max(0, int(time_remaining.total_seconds() / 60))
    seconds_remaining = max(0, int(time_remaining.total_seconds() % 60))
    
    # Show which questions have been answered
    answered_questions = []
    if user_id in state["user_answers"]:
        answered_questions = [q_idx + 1 for q_idx in state["user_answers"][user_id].keys()]
        answered_questions.sort()
    
    answered_text = ", ".join(map(str, answered_questions)) if answered_questions else "None"
    
    discord_logger.debug(f"User {interaction.user.name}({user_id}) progress check: {answered_count}/{total_q} questions answered")
    
    await interaction.response.send_message(
        f"📊 **Your Quiz Progress:**\n"
        f"Answered: {answered_count}/{total_q} questions\n"
        f"Questions answered: {answered_text}\n"
        f"⏱️ Time remaining: {minutes_remaining}m {seconds_remaining}s",
        ephemeral=True
    )


@tree.command(name="info", description="Show bot information and stats")
async def info_command(interaction: discord.Interaction):
    """Display bot information."""
    discord_logger.debug(f"/info command: user={interaction.user.name}({interaction.user.id}) guild={interaction.guild.name if interaction.guild else 'DM'}({interaction.guild_id if interaction.guild else 'N/A'}) channel={interaction.channel_id}")
    
    # Check permissions first
    has_perms, perm_error = await check_bot_permissions(interaction)
    if not has_perms:
        await interaction.response.send_message(perm_error, ephemeral=True)
        return
    
    # Check if this guild is configured
    guild_key = str(interaction.guild_id) if interaction.guild_id else None
    is_configured = guild_key and guild_key in GUILD_CONFIGS and "assistant_id" in GUILD_CONFIGS[guild_key]
    
    embed = discord.Embed(
        title="🎯 OPSObot",
        description="AI-powered Q&A and quiz bot for DCS Squadron SOPs",
        color=0x2d5016  # Forest green
    )
    embed.add_field(name="Model", value="GPT-4 (via OpenAI Assistants)", inline=True)
    embed.add_field(name="Servers", value=str(len(client.guilds)), inline=True)
    embed.add_field(name="Version", value="2.0.0", inline=True)
    
    if is_configured:
        embed.add_field(name="Server Status", value="✅ Configured", inline=False)
        # Show document count if available
        doc_count = len(GUILD_CONFIGS[guild_key].get("documents", []))
        embed.add_field(name="Documents", value=str(doc_count), inline=True)
    else:
        embed.add_field(name="Server Status", value="⚠️ Not configured - Admin needs to run `/setup`", inline=False)
    
    embed.add_field(
        name="Commands",
        value="• `/setup` - Configure bot (admin only)\n"
              "• `/upload` - Upload SOP documents (admin only)\n"
              "• `/list_documents` - View uploaded documents\n"
              "• `/ask` - Ask questions about SOPs\n"
              "• `/quiz_start` - Start timed quiz\n"
              "• `/quiz_answer` - Answer question\n"
              "• `/quiz_score` - View progress\n"
              "• `/quiz_end` - End quiz",
        inline=False
    )
    embed.set_footer(text="Powered by OpenAI Assistants API v2")
    
    await interaction.response.send_message(embed=embed)


@tree.command(name="setup", description="Configure the bot for this server (admin only)")
async def setup_command(interaction: discord.Interaction, api_key: str):
    """Configure OpenAI API key and create assistant for this guild."""
    discord_logger.info(f"/setup command: user={interaction.user.name}({interaction.user.id}) guild={interaction.guild.name if interaction.guild else 'DM'}({interaction.guild_id})")
    
    # Only allow in guilds, not DMs
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        return
    
    # Check if user is admin
    if not interaction.user.guild_permissions.administrator:
        discord_logger.warning(f"/setup denied: user {interaction.user.name}({interaction.user.id}) is not admin")
        await interaction.response.send_message("❌ You need Administrator permissions to use this command.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True, thinking=True)
    
    try:
        # Create OpenAI client with provided key
        test_client = OpenAI(
            api_key=api_key,
            default_headers={"OpenAI-Beta": "assistants=v2"}
        )
        
        # Create a new assistant for this guild
        assistant = test_client.beta.assistants.create(
            name=f"OPSObot - {interaction.guild.name}",
            instructions="""You are an expert assistant for DCS (Digital Combat Simulator) squadron Standard Operating Procedures (SOPs).
            
Your role is to:
- Answer questions based ONLY on the uploaded SOP documents
- Provide accurate page numbers when citing information
- Generate quiz questions to test squadron members' knowledge
- Help squadron members learn and stay sharp on their procedures

When answering questions:
- Always cite page numbers from the documents
- If information isn't in the documents, clearly state that
- Be concise but thorough
- Focus on practical application

When generating quiz questions:
- Create diverse questions covering different topics
- Include 4 multiple choice options
- Provide clear explanations with page references
- Focus on operationally relevant knowledge""",
            model="gpt-4o-mini",
            tools=[{"type": "file_search"}]
        )
        
        # Create a vector store for documents
        vector_store = test_client.beta.vector_stores.create(
            name=f"OPSObot - {interaction.guild.name} - SOPs"
        )
        
        # Update assistant to use vector store
        test_client.beta.assistants.update(
            assistant_id=assistant.id,
            tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}}
        )
        
        # Store configuration
        guild_key = str(interaction.guild_id)
        GUILD_CONFIGS[guild_key] = {
            "api_key": api_key,
            "assistant_id": assistant.id,
            "vector_store_id": vector_store.id,
            "documents": [],
            "configured_at": datetime.utcnow().isoformat(),
            "configured_by": str(interaction.user.id)
        }
        save_guild_configs(GUILD_CONFIGS)
        
        discord_logger.info(f"Setup complete for guild {interaction.guild.name}({interaction.guild_id}): assistant={assistant.id}")
        
        await interaction.followup.send(
            f"✅ **Setup Complete!**\n\n"
            f"• OpenAI API key configured\n"
            f"• Assistant created: `{assistant.id}`\n"
            f"• Vector store created: `{vector_store.id}`\n\n"
            f"Next steps:\n"
            f"1. Use `/upload` to upload your SOP documents\n"
            f"2. Use `/ask` to ask questions about your SOPs\n"
            f"3. Use `/quiz_start` to test your squadron's knowledge\n\n"
            f"⚠️ **Security Note:** Your API key is stored locally and used only for this server.",
            ephemeral=True
        )
        
    except Exception as e:
        discord_logger.error(f"Setup failed for guild {interaction.guild_id}: {e}", exc_info=True)
        await interaction.followup.send(
            f"❌ **Setup Failed**\n\n"
            f"Error: {str(e)}\n\n"
            f"Please check:\n"
            f"• Your API key is valid\n"
            f"• Your API key has sufficient credits\n"
            f"• You have access to the Assistants API",
            ephemeral=True
        )


@tree.command(name="upload", description="Upload SOP documents to the bot (admin only)")
async def upload_command(interaction: discord.Interaction, document: discord.Attachment):
    """Upload a document to the guild's assistant."""
    discord_logger.info(f"/upload command: user={interaction.user.name}({interaction.user.id}) guild={interaction.guild.name if interaction.guild else 'DM'}({interaction.guild_id}) file={document.filename}")
    
    # Only allow in guilds
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        return
    
    # Check if user is admin
    if not interaction.user.guild_permissions.administrator:
        discord_logger.warning(f"/upload denied: user {interaction.user.name}({interaction.user.id}) is not admin")
        await interaction.response.send_message("❌ You need Administrator permissions to use this command.", ephemeral=True)
        return
    
    # Check if guild is configured
    guild_key = str(interaction.guild_id)
    if guild_key not in GUILD_CONFIGS or "assistant_id" not in GUILD_CONFIGS[guild_key]:
        await interaction.response.send_message("❌ This server hasn't been configured yet. Run `/setup` first.", ephemeral=True)
        return
    
    # Check file type (only allow PDFs for now)
    if not document.filename.lower().endswith('.pdf'):
        await interaction.response.send_message("❌ Only PDF files are supported currently.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True, thinking=True)
    
    try:
        # Download the file
        file_data = await document.read()
        
        # Get OpenAI client for this guild
        oai = get_openai_client(interaction.guild_id)
        if not oai:
            await interaction.followup.send("❌ Failed to get OpenAI client.", ephemeral=True)
            return
        
        # Upload file to OpenAI
        file_obj = oai.files.create(
            file=(document.filename, file_data),
            purpose="assistants"
        )
        
        # Add file to vector store
        vector_store_id = GUILD_CONFIGS[guild_key]["vector_store_id"]
        oai.beta.vector_stores.files.create(
            vector_store_id=vector_store_id,
            file_id=file_obj.id
        )
        
        # Update config
        if "documents" not in GUILD_CONFIGS[guild_key]:
            GUILD_CONFIGS[guild_key]["documents"] = []
        
        GUILD_CONFIGS[guild_key]["documents"].append({
            "filename": document.filename,
            "file_id": file_obj.id,
            "uploaded_at": datetime.utcnow().isoformat(),
            "uploaded_by": str(interaction.user.id),
            "size_bytes": len(file_data)
        })
        save_guild_configs(GUILD_CONFIGS)
        
        discord_logger.info(f"Document uploaded for guild {interaction.guild_id}: {document.filename} (file_id={file_obj.id})")
        
        await interaction.followup.send(
            f"✅ **Document Uploaded!**\n\n"
            f"• Filename: `{document.filename}`\n"
            f"• File ID: `{file_obj.id}`\n"
            f"• Size: {len(file_data) / 1024:.1f} KB\n\n"
            f"The document is now available for questions and quizzes!",
            ephemeral=True
        )
        
    except Exception as e:
        discord_logger.error(f"Upload failed for guild {interaction.guild_id}: {e}", exc_info=True)
        await interaction.followup.send(
            f"❌ **Upload Failed**\n\n"
            f"Error: {str(e)}",
            ephemeral=True
        )


@tree.command(name="list_documents", description="List all uploaded SOP documents")
async def list_documents_command(interaction: discord.Interaction):
    """List all documents uploaded to this guild's assistant."""
    discord_logger.info(f"/list_documents command: user={interaction.user.name}({interaction.user.id}) guild={interaction.guild.name if interaction.guild else 'DM'}({interaction.guild_id})")
    
    # Only allow in guilds
    if not interaction.guild:
        await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        return
    
    # Check if guild is configured
    guild_key = str(interaction.guild_id)
    if guild_key not in GUILD_CONFIGS or "assistant_id" not in GUILD_CONFIGS[guild_key]:
        await interaction.response.send_message("❌ This server hasn't been configured yet. Run `/setup` first.", ephemeral=True)
        return
    
    documents = GUILD_CONFIGS[guild_key].get("documents", [])
    
    if not documents:
        await interaction.response.send_message(
            "📚 **No documents uploaded yet.**\n\n"
            "Use `/upload` to add SOP documents (admin only).",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="📚 Uploaded SOP Documents",
        description=f"{len(documents)} document(s) available",
        color=0x2d5016
    )
    
    for i, doc in enumerate(documents, 1):
        uploaded_at = datetime.fromisoformat(doc["uploaded_at"]).strftime("%Y-%m-%d %H:%M UTC")
        size_kb = doc.get("size_bytes", 0) / 1024
        
        embed.add_field(
            name=f"{i}. {doc['filename']}",
            value=f"Uploaded: {uploaded_at}\nSize: {size_kb:.1f} KB\nFile ID: `{doc['file_id']}`",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@client.event
async def on_ready():
    """Called when the bot is ready."""
    await tree.sync()
    discord_logger.info(f"🎯 OPSObot is online!")
    discord_logger.info(f"📚 Connected to {len(client.guilds)} server(s)")
    discord_logger.info(f"🤖 Using GPT-4 with Assistants API v2")
    discord_logger.info(f"Bot user: {client.user.name}#{client.user.discriminator} (ID: {client.user.id})")
    
    # Log guild information
    for guild in client.guilds:
        guild_key = str(guild.id)
        is_configured = guild_key in GUILD_CONFIGS and "assistant_id" in GUILD_CONFIGS[guild_key]
        status = "✅ Configured" if is_configured else "⚠️ Not configured"
        discord_logger.info(f"  - Guild: {guild.name} (ID: {guild.id}, Members: {guild.member_count}) - {status}")
    
    print(f"🎯 OPSObot is online!")
    print(f"📚 Connected to {len(client.guilds)} server(s)")
    print(f"🤖 Using GPT-4 with Assistants API v2")


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
