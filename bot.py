import discord
import os
import requests
import edge_tts
import asyncio
import re
import tempfile
from duckduckgo_search import DDGS

# === CONFIGURATION ===
VOICE_ENABLED = True
VOICE_NAME = "en-GB-SoniaNeural"
MODEL_NAME = "llama-3.3-70b-versatile"

# === DISCORD SETUP ===
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# === WEB SEARCH (DuckDuckGo - FREE!) ===
async def search_web(query):
    """Search using DuckDuckGo - no API key needed!"""
    try:
        def _search():
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=3))
                return results
        
        results = await asyncio.to_thread(_search)
        
        if not results:
            return None
        
        context_parts = []
        total_length = 0
        MAX_TOTAL = 2500
        
        for r in results[:3]:
            content = r.get('body', '')[:400]
            url = r.get('href', '')
            title = r.get('title', '')
            part = f"Title: {title}\nSource: {url}\n{content}"
            
            if total_length + len(part) > MAX_TOTAL:
                break
            
            context_parts.append(part)
            total_length += len(part)
        
        if context_parts:
            return "\n\n".join(context_parts)
        return None
    except Exception as e:
        print(f"❌ Search error: {e}")
        return None

# === AI WITH AUTO WEB SEARCH ===
async def get_ai_response(user_message, username, ctx_channel=None):
    try:
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            return "❌ GROQ_API_KEY not set!"
        
        # Detect if search is needed
        needs_search_keywords = [
            'today', 'now', 'current', 'latest', 'recent', 'news',
            'weather', 'price', 'score', 'update', 'happening',
            'this week', 'this month', 'this year', 'yesterday', 'tomorrow',
            'live', 'breaking', 'winner', 'who won', 'world cup', 'worldcup',
            '2026', '2025', '2024', 'president', 'election', 'stock',
            'crypto', 'bitcoin', 'match', 'game', 'tournament'
        ]
        
        message_lower = user_message.lower()
        needs_search = any(keyword in message_lower for keyword in needs_search_keywords)
        
        search_context = ""
        if needs_search:
            if ctx_channel:
                await ctx_channel.send('🔍 *Searching the web...*')
            
            search_context = await search_web(user_message)
            if search_context:
                search_context = f"\n\n=== CURRENT WEB INFORMATION ===\n{search_context}\n=== END ===\n\nUse the above web search results to provide up-to-date information. Always cite source URLs."
                print(f"✅ Search context: {len(search_context)} chars")
            else:
                if ctx_channel:
                    await ctx_channel.send('⚠️ *No search results, using my training data.*')
        
        full_prompt = user_message + search_context
        
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {groq_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': MODEL_NAME,
                'messages': [
                    {'role': 'system', 'content': f'You are ShobJanta AI powered by Llama 3.3 70B. Chatting with {username}. You have access to real-time web search. Be concise (under 300 words), helpful, and always cite sources. Use Discord-friendly formatting.'},
                    {'role': 'user', 'content': full_prompt}
                ],
                'max_tokens': 800,
                'temperature': 0.7
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        elif response.status_code == 413:
            return await get_ai_response_no_search(user_message, username)
        else:
            return f'❌ API error: {response.status_code}'
    except Exception as e:
        return f'❌ Error: {str(e)}'

async def get_ai_response_no_search(user_message, username):
    try:
        groq_key = os.getenv("GROQ_API_KEY")
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {groq_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': MODEL_NAME,
                'messages': [
                    {'role': 'system', 'content': f'You are ShobJanta AI chatting with {username}. Be concise.'},
                    {'role': 'user', 'content': user_message}
                ],
                'max_tokens': 500,
                'temperature': 0.7
            },
            timeout=20
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return f'❌ API error: {response.status_code}'
    except Exception as e:
        return f'❌ Error: {str(e)}'

# === SPEECH-TO-TEXT (Voice → Text) ===
async def transcribe_voice(audio_url):
    try:
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            return None, "❌ GROQ_API_KEY not set!"
        
        audio_data = requests.get(audio_url, timeout=30)
        
        if audio_data.status_code != 200:
            return None, f"❌ Failed to download: {audio_data.status_code}"
        
        files = {'file': ('voice.ogg', audio_data.content, 'audio/ogg')}
        data = {'model': 'whisper-large-v3', 'response_format': 'json', 'language': 'en'}
        headers = {'Authorization': f'Bearer {groq_key}'}
        
        response = requests.post(
            'https://api.groq.com/openai/v1/audio/transcriptions',
            headers=headers, files=files, data=data, timeout=60
        )
        
        if response.status_code == 200:
            transcript = response.json().get('text', '').strip()
            return (transcript, None) if transcript else (None, "❌ Could not understand")
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
    print(f'Model: {MODEL_NAME}')
    print(f'Voice: {VOICE_NAME}')
    print(f'Web Search: ✅ DuckDuckGo (FREE)')
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
    
    if content == '!model':
        await message.channel.send(
            f'🤖 **Model:** `{MODEL_NAME}`\n'
            f'🌐 **Web Search:** ✅ DuckDuckGo (FREE)\n'
            f'🔊 **Voice:** `{VOICE_NAME}`'
        )
        return
    
    if content == '!voice on':
        VOICE_ENABLED = True
        await message.channel.send('🔊 **Voice ENABLED**')
        return
    
    if content == '!voice off':
        VOICE_ENABLED = False
        await message.channel.send('🔇 **Voice disabled**')
        return
    
    if content == '!voice':
        status = '🔊 ON' if VOICE_ENABLED else '🔇 OFF'
        await message.channel.send(f'Voice: **{status}**')
        return
    
    if content.startswith('!search '):
        query = content[8:]
        async with message.channel.typing():
            await message.channel.send('🔍 *Searching DuckDuckGo...*')
            results = await search_web(query)
            if results:
                await message.channel.send(f'**Results for:** {query}\n\n{results[:1900]}')
            else:
                await message.channel.send('❌ No results found')
        return
    
    if content == '!help':
        embed = discord.Embed(
            title='🤖 ShobJanta AI',
            description='AI with voice + web search!',
            color=0x00ff00
        )
        embed.add_field(name='💬 Chat', value='Type any message!', inline=False)
        embed.add_field(name='🌐 Web Search', value='**Auto** for current events | `!search [query]`', inline=False)
        embed.add_field(name='🎤 Voice Input', value='Send voice message!', inline=False)
        embed.add_field(name='🔊 Voice Output', value='`!voice on/off`', inline=False)
        embed.add_field(name='🛠️ Commands', value='`!ping` `!model` `!search` `!voice` `!help`', inline=False)
        embed.set_footer(text='Powered by Llama 3.3 + DuckDuckGo + Edge TTS')
        await message.channel.send(embed=embed)
        return
    
    # === VOICE MESSAGE INPUT ===
    if message.attachments:
        for attachment in message.attachments:
            if attachment.content_type and 'audio' in attachment.content_type:
                async with message.channel.typing():
                    await message.channel.send('🎤 *Listening...*')
                    transcript, error = await transcribe_voice(attachment.url)
                    if error:
                        await message.channel.send(error)
                        return
                    if not transcript:
                        await message.channel.send('❌ Could not understand')
                        return
                    await message.channel.send(f'📝 *I heard:* "{transcript}"')
                    ai_reply = await get_ai_response(transcript, message.author.name, message.channel)
                    if len(ai_reply) > 2000:
                        ai_reply = ai_reply[:1997] + '...'
                    await message.channel.send(ai_reply)
                    if VOICE_ENABLED:
                        audio_file = await text_to_speech(ai_reply)
                        if audio_file:
                            try:
                                voice_file = discord.File(audio_file, filename="voice-message.mp3")
                                await message.channel.send("🔊 *Voice reply:*", file=voice_file)
                            finally:
                                try:
                                    os.remove(audio_file)
                                except:
                                    pass
                return
    
    # === TEXT MESSAGE INPUT ===
    if content:
        async with message.channel.typing():
            ai_reply = await get_ai_response(content, message.author.name, message.channel)
            if len(ai_reply) > 2000:
                ai_reply = ai_reply[:1997] + '...'
            await message.channel.send(ai_reply)
            if VOICE_ENABLED:
                audio_file = await text_to_speech(ai_reply)
                if audio_file:
                    try:
                        voice_file = discord.File(audio_file, filename="voice-message.mp3")
                        await message.channel.send("🔊 *Voice message:*", file=voice_file)
                    finally:
                        try:
                            os.remove(audio_file)
                        except:
                            pass

# === RUN BOT ===
bot.run(os.getenv("DISCORD_TOKEN"))
