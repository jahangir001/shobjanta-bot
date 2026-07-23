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

# === WEB SEARCH (DuckDuckGo with error handling) ===
async def search_web(query):
    """Search using DuckDuckGo with multiple fallback methods"""
    try:
        print(f"🔍 Searching for: {query}")
        
        # Method 1: Try DDGS library
        def _search_ddgs():
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=3))
                    return results
            except Exception as e:
                print(f"DDGS error: {e}")
                return []
        
        results = await asyncio.to_thread(_search_ddgs)
        
        if results and len(results) > 0:
            print(f"✅ Got {len(results)} results from DDGS")
            
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
        
        print("⚠️ DDGS returned no results, trying fallback...")
        
        # Method 2: Fallback to direct DuckDuckGo HTML scraping
        def _search_html():
            try:
                url = "https://html.duckduckgo.com/html/"
                data = {'q': query, 'b': ''}
                response = requests.post(url, data=data, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }, timeout=10)
                
                if response.status_code == 200:
                    # Simple parsing - extract text snippets
                    import re
                    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', response.text, re.DOTALL)
                    urls = re.findall(r'class="result__url"[^>]*>(.*?)</a>', response.text, re.DOTALL)
                    
                    parts = []
                    for i, snippet in enumerate(snippets[:3]):
                        url_text = urls[i].strip() if i < len(urls) else ""
                        # Clean HTML tags
                        clean_snippet = re.sub(r'<[^>]+>', '', snippet).strip()[:400]
                        if clean_snippet:
                            parts.append(f"Source: {url_text}\n{clean_snippet}")
                    
                    return "\n\n".join(parts) if parts else None
                return None
            except Exception as e:
                print(f"HTML scrape error: {e}")
                return None
        
        html_results = await asyncio.to_thread(_search_html)
        if html_results:
            print(f"✅ Got results from HTML scraping")
            return html_results
        
        print("❌ All search methods failed")
        return None
        
    except Exception as e:
        print(f"❌ Search exception: {e}")
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
            'crypto', 'bitcoin', 'match', 'game', 'tournament', 'result'
        ]
        
        message_lower = user_message.lower()
        needs_search = any(keyword in message_lower for keyword in needs_search_keywords)
        
        search_context = ""  # ← Always start as empty string!
        if needs_search:
            if ctx_channel:
                await ctx_channel.send('🔍 *Searching the web...*')
            
            search_result = await search_web(user_message)
            
            # ← FIX: Check if result is not None before concatenating!
            if search_result and search_result.strip():
                search_context = f"\n\n=== CURRENT WEB INFORMATION ===\n{search_result}\n=== END ===\n\nUse the above web search results to provide up-to-date information. Always cite source URLs."
                print(f"✅ Search context: {len(search_context)} chars")
            else:
                if ctx_channel:
                    await ctx_channel.send('⚠️ *No search results, using my training data.*')
        
        # ← FIX: Safe concatenation
        full_prompt = user_message
        if search_context and search_context.strip():
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

# === SPEECH-TO-TEXT ===
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

# === TEXT-TO-SPEECH ===
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
    print(f'Web Search: ✅ DuckDuckGo (with fallback)')
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
            f'🌐 **Web Search:** ✅ DuckDuckGo\n'
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
                await message.channel.send('❌ No results found. Try different keywords.')
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

bot.run(os.getenv("DISCORD_TOKEN"))
