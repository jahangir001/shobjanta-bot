import discord
import os
import requests
import edge_tts
import asyncio
import re
import tempfile

# === CONFIGURATION ===
VOICE_ENABLED = True
VOICE_NAME = "en-US-AriaNeural"

# === DISCORD SETUP ===
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# === AI FUNCTION ===
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
                'model': 'llama-3.1-8b-instant',
                'messages': [
                    {'role': 'system', 'content': f'You are ShobJanta AI, a Discord assistant powered by Llama 3.1 70B. You are chatting with {username}. Be concise (under 300 words), helpful, and friendly.'},
                    {'role': 'user', 'content': user_message}
                ],
                'max_tokens': 800,
                'temperature': 0.7
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return f'❌ API error: {response.status_code}'
    except Exception as e:
        return f'❌ Error: {str(e)}'

# === SPEECH-TO-TEXT (Voice → Text) ===
async def transcribe_voice(audio_url):
    """Download Discord voice message and transcribe it using Groq Whisper"""
    try:
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            return None, "❌ GROQ_API_KEY not set!"
        
        # Step 1: Download the audio file from Discord
        # Discord voice messages need special auth header
        async with message.channel.typing():
            # Get the audio file
            audio_data = requests.get(audio_url, timeout=30)
        
        if audio_data.status_code != 200:
            return None, f"❌ Failed to download audio: {audio_data.status_code}"
        
        # Step 2: Send to Groq Whisper for transcription
        # Groq offers FREE Whisper API!
        files = {
            'file': ('voice.ogg', audio_data.content, 'audio/ogg'),
        }
        data = {
            'model': 'whisper-large-v3',  # Groq's Whisper model
            'response_format': 'json',
            'language': 'en',  # Optional: auto-detect if not specified
        }
        headers = {
            'Authorization': f'Bearer {groq_key}'
        }
        
        response = requests.post(
            'https://api.groq.com/openai/v1/audio/transcriptions',
            headers=headers,
            files=files,
            data=data,
            timeout=60
        )
        
        if response.status_code == 200:
            transcript = response.json().get('text', '').strip()
            if transcript:
                return transcript, None
            else:
                return None, "❌ Could not understand the voice message"
        else:
            return None, f"❌ Transcription error: {response.status_code}"
    
    except Exception as e:
        return None, f"❌ Error: {str(e)}"

# === TEXT-TO-SPEECH (Text → Voice) ===
async def text_to_speech(text):
    try:
        clean_text = text
        clean_text = re.sub(r'```[\s\S]*?```', 'code block', clean_text)
        clean_text = re.sub(r'`[^`]+`', '', clean_text)
        clean_text = re.sub(r'http\S+', 'link', clean_text)
        clean_text = re.sub(r'[*_~#>`]', '', clean_text)
        clean_text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF✅❌⚠️🎉🎊]', '', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        if len(clean_text) > 1000:
            clean_text = clean_text[:997] + "..."
        
        if not clean_text:
            return None
        
        communicate = edge_tts.Communicate(clean_text, VOICE_NAME)
        
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
    print(f'Voice OUT: {"ON" if VOICE_ENABLED else "OFF"}')
    print(f'Voice IN: ON (Whisper)')
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
        await message.channel.send(f'Voice output: **{status}**\nVoice input: **🎤 ON** (always listening!)\nType `!voice on/off` to toggle output.')
        return
    
    if content == '!help':
        embed = discord.Embed(
            title='🤖 ShobJanta AI - Voice Edition',
            description='AI assistant with voice support!',
            color=0x00ff00
        )
        embed.add_field(
            name='💬 Text Chat',
            value='Just type any message!',
            inline=False
        )
        embed.add_field(
            name='🎤 Voice Input',
            value='**Send a voice message!** I will listen and transcribe it.',
            inline=False
        )
        embed.add_field(
            name='🔊 Voice Output',
            value='`!voice on/off` - Toggle voice replies',
            inline=False
        )
        embed.add_field(
            name='🛠️ Commands',
            value='`!ping` `!help` `!voice`',
            inline=False
        )
        embed.set_footer(text='Powered by Llama 3.1 70B + Whisper + Edge TTS')
        await message.channel.send(embed=embed)
        return
    
    # === VOICE MESSAGE INPUT ===
    # Check if message has audio attachment (voice message)
    if message.attachments:
        for attachment in message.attachments:
            # Check if it's an audio file
            if attachment.content_type and 'audio' in attachment.content_type:
                async with message.channel.typing():
                    await message.channel.send('🎤 *Listening to your voice message...*')
                    
                    # Transcribe the voice message
                    transcript, error = await transcribe_voice(attachment.url)
                    
                    if error:
                        await message.channel.send(error)
                        return
                    
                    if not transcript:
                        await message.channel.send('❌ Could not understand the audio')
                        return
                    
                    # Show what we heard
                    await message.channel.send(f'📝 *I heard:* "{transcript}"')
                    
                    # Get AI response
                    ai_reply = await get_ai_response(transcript, message.author.name)
                    
                    # Send text reply
                    if len(ai_reply) > 2000:
                        ai_reply = ai_reply[:1997] + '...'
                    await message.channel.send(ai_reply)
                    
                    # Send voice reply if enabled
                    if VOICE_ENABLED:
                        audio_file = await text_to_speech(ai_reply)
                        if audio_file:
                            try:
                                voice_file = discord.File(audio_file, filename="voice-message.mp3")
                                await message.channel.send(
                                    content="🔊 *Voice reply:*",
                                    file=voice_file
                                )
                            finally:
                                try:
                                    os.remove(audio_file)
                                except:
                                    pass
                return  # Processed voice message, exit
    
    # === TEXT MESSAGE INPUT ===
    async with message.channel.typing():
        ai_reply = await get_ai_response(content, message.author.name)
        
        if len(ai_reply) > 2000:
            ai_reply = ai_reply[:1997] + '...'
        await message.channel.send(ai_reply)
        
        if VOICE_ENABLED:
            audio_file = await text_to_speech(ai_reply)
            if audio_file:
                try:
                    voice_file = discord.File(audio_file, filename="voice-message.mp3")
                    await message.channel.send(
                        content="🔊 *Voice message:*",
                        file=voice_file
                    )
                finally:
                    try:
                        os.remove(audio_file)
                    except:
                        pass

# === RUN BOT ===
bot.run(os.getenv("DISCORD_TOKEN"))
