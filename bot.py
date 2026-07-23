import discord
import os
import requests
import edge_tts
import asyncio
import re
import tempfile

# === CONFIGURATION ===
VOICE_ENABLED = True  # Bot sends voice messages by default
VOICE_NAME = "en-US-AriaNeural"  # Female voice (see options below)

# === DISCORD SETUP ===
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# === AI FUNCTION (Groq) ===
async def get_ai_response(user_message, username):
    try:
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            return "❌ GROQ_API_KEY not set!"
        
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {groq_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'llama-3.3-70b-versatile',
                'messages': [
                    {'role': 'system', 'content': f'You are ShobJanta AI, a Discord assistant powered by Llama 3.1 70B. You are chatting with {username}. Be concise (under 300 words), helpful, and friendly. Use Discord-friendly formatting.'},
                    {'role': 'user', 'content': user_message}
                ],
                'max_tokens': 800,
                'temperature': 0.7
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f'❌ API error: {response.status_code}'
    except Exception as e:
        return f'❌ Error: {str(e)}'

# === TEXT-TO-SPEECH FUNCTION ===
async def text_to_speech(text):
    """Convert text to speech using Microsoft Edge TTS (free, high quality)"""
    try:
        # Clean text for speech (remove markdown, emojis, URLs, code blocks)
        clean_text = text
        # Remove code blocks
        clean_text = re.sub(r'```[\s\S]*?```', 'code block', clean_text)
        clean_text = re.sub(r'`[^`]+`', '', clean_text)
        # Remove URLs
        clean_text = re.sub(r'http\S+', 'link', clean_text)
        # Remove markdown formatting
        clean_text = re.sub(r'[*_~#>`]', '', clean_text)
        # Remove emojis (basic)
        clean_text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF✅❌⚠️🎉🎊]', '', clean_text)
        # Remove extra whitespace
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Limit length (Discord voice message limit is 5 min, but keep it short)
        if len(clean_text) > 1000:
            clean_text = clean_text[:997] + "..."
        
        if not clean_text:
            return None
        
        # Generate speech file
        communicate = edge_tts.Communicate(clean_text, VOICE_NAME)
        
        # Use temp file (gets deleted automatically)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
            tmp_path = tmp_file.name
        
        await communicate.save(tmp_path)
        return tmp_path
    
    except Exception as e:
        print(f'TTS Error: {e}')
        return None

# === BOT EVENTS ===
@bot.event
async def on_ready():
    print('=' * 50)
    print(f'✅ Bot ONLINE: {bot.user}')
    print(f'Voice: {"ON" if VOICE_ENABLED else "OFF"}')
    print(f'Voice: {VOICE_NAME}')
    print(f'Servers: {len(bot.guilds)}')
    print('=' * 50)

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    global VOICE_ENABLED
    content = message.content.strip()
    
    # === COMMANDS ===
    if content == '!ping':
        await message.channel.send('🏓 Pong!')
        return
    
    if content == '!voice on':
        VOICE_ENABLED = True
        await message.channel.send('🔊 **Voice messages ENABLED!** I will speak my replies.')
        return
    
    if content == '!voice off':
        VOICE_ENABLED = False
        await message.channel.send('🔇 **Voice messages disabled.** Text-only mode.')
        return
    
    if content == '!voice':
        status = '🔊 ON' if VOICE_ENABLED else '🔇 OFF'
        await message.channel.send(f'Voice messages: **{status}**\nCurrent voice: `{VOICE_NAME}`\nType `!voice on/off` to toggle.')
        return
    
    if content == '!help':
        embed = discord.Embed(
            title='🤖 ShobJanta AI',
            description='AI-powered Discord assistant with voice support!',
            color=0x00ff00
        )
        embed.add_field(
            name='💬 Chat',
            value='Just type any message to chat!',
            inline=False
        )
        embed.add_field(
            name='🎙️ Voice Commands',
            value='`!voice` - Check voice status\n`!voice on` - Enable voice\n`!voice off` - Disable voice',
            inline=False
        )
        embed.add_field(
            name='🛠️ Utility',
            value='`!ping` - Test bot\n`!help` - This message',
            inline=False
        )
        embed.set_footer(text='Powered by Llama 3.1 70B + Edge TTS')
        await message.channel.send(embed=embed)
        return
    
    # === AI RESPONSE ===
    async with message.channel.typing():
        # Get AI text response
        ai_reply = await get_ai_response(content, message.author.name)
        
        # Send text reply
        if len(ai_reply) > 2000:
            ai_reply = ai_reply[:1997] + '...'
        await message.channel.send(ai_reply)
        
        # Send voice message if enabled
        if VOICE_ENABLED:
            audio_file = await text_to_speech(ai_reply)
            if audio_file:
                try:
                    # Send as Discord voice message
                    voice_file = discord.File(audio_file, filename="voice-message.mp3")
                    await message.channel.send(
                        content="🔊 *Voice message:*",
                        file=voice_file
                    )
                finally:
                    # Clean up temp file
                    try:
                        os.remove(audio_file)
                    except:
                        pass

# === RUN BOT ===
bot.run(os.getenv("DISCORD_TOKEN"))
