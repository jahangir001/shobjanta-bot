import discord
import os
import requests
import edge_tts
import asyncio
import re
import tempfile

# === CONFIGURATION ===
VOICE_ENABLED = True
VOICE_NAME = "en-GB-SoniaNeural"
MODEL_NAME = "llama-3.3-70b-versatile"

# === DISCORD SETUP ===
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

# === WEB SEARCH (Multiple methods, ultra-safe) ===
async def search_web(query):
    """Search the web with multiple methods - gets current info!"""
    
    # Method 1: Google News RSS (BEST for current events!)
    try:
        import urllib.parse
        import xml.etree.ElementTree as ET
        
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
        
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.content)
                items = root.findall('.//item')
                
                if items:
                    parts = []
                    for i, item in enumerate(items[:5]):  # Top 5 news
                        title = item.find('title').text if item.find('title') is not None else ''
                        pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
                        source = item.find('source').text if item.find('source') is not None else 'Unknown'
                        
                        if title:
                            parts.append(f"[{i+1}] {title}\nSource: {source}\nPublished: {pub_date}")
                    
                    if parts:
                        return "=== LATEST NEWS ===\n" + "\n\n".join(parts)
            except ET.ParseError:
                pass
    except Exception as e:
        print(f"Google News error: {e}")
    
    # Method 2: Wikipedia (full article content)
    try:
        # Search for relevant pages
        search_response = requests.get(
            'https://en.wikipedia.org/w/api.php',
            params={
                'action': 'query',
                'list': 'search',
                'srsearch': query,
                'format': 'json',
                'srlimit': 2
            },
            timeout=10
        )
        
        if search_response.status_code == 200:
            data = search_response.json()
            results = data.get('query', {}).get('search', [])
            
            if results:
                # Get full content of top result
                titles = [results[0]['title']]
                
                content_response = requests.get(
                    'https://en.wikipedia.org/w/api.php',
                    params={
                        'action': 'query',
                        'titles': titles[0],
                        'prop': 'extracts',
                        'exintro': False,
                        'explaintext': True,
                        'format': 'json'
                    },
                    timeout=10
                )
                
                if content_response.status_code == 200:
                    content_data = content_response.json()
                    pages = content_data.get('query', {}).get('pages', {})
                    
                    for page_id, page_data in pages.items():
                        if page_id != '-1':
                            extract = page_data.get('extract', '')
                            if extract and len(extract) > 200:
                                # Truncate to 2000 chars but keep important parts
                                return f"=== Wikipedia: {titles[0]} ===\n{extract[:2000]}"
    except Exception as e:
        print(f"Wikipedia error: {e}")
    
    # Method 3: DuckDuckGo instant answer (for quick facts)
    try:
        response = requests.get(
            'https://api.duckduckgo.com/',
            params={
                'q': query,
                'format': 'json',
                'no_html': 1,
                'skip_disambig': 1
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            abstract = data.get('Abstract', '')
            answer = data.get('Answer', '')
            
            if abstract:
                return f"=== Quick Info ===\n{abstract[:1500]}"
            elif answer:
                return f"=== Answer ===\n{answer}"
    except Exception as e:
        print(f"DDG instant answer error: {e}")
    
    return ""

# === AI WITH WEB SEARCH (100% safe from None errors) ===
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
        
        # ALWAYS start with empty string, never None
        search_results_text = ""
        
        if needs_search:
            try:
                if ctx_channel:
                    await ctx_channel.send('🔍 *Searching the web...*')
                
                # Get search results (returns "" if fails, never None)
                search_results_text = await search_web(user_message)
                
                # Extra safety: ensure it's a string
                if not isinstance(search_results_text, str):
                    search_results_text = ""
                
                if search_results_text and search_results_text.strip():
                    if ctx_channel:
                        await ctx_channel.send('✅ *Found information!*')
                else:
                    search_results_text = ""
                    if ctx_channel:
                        await ctx_channel.send('⚠️ *No results, using training data*')
                        
            except Exception as e:
                print(f"Search error in get_ai_response: {e}")
                search_results_text = ""
        
        # Build prompt with ULTRA-SAFE string handling
        user_prompt = str(user_message) if user_message else ""
        
        if search_results_text and search_results_text.strip():
            # Only add search context if we actually have it
            user_prompt = user_prompt + "\n\n=== WEB SEARCH RESULTS ===\n" + search_results_text + "\n=== END ===\n\nUse these search results to provide accurate, up-to-date information. Cite source URLs."
        
        # Make sure user_prompt is never None
        if not user_prompt:
            user_prompt = "Hello"
        
        # Call Groq AI
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {groq_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': MODEL_NAME,
                'messages': [
                    {'role': 'system', 'content': f'You are ShobJanta AI powered by Llama 3.3 70B. Chatting with {username}. Be concise (under 300 words) and helpful. Use Discord-friendly formatting.'},
                    {'role': 'user', 'content': user_prompt}
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
        if not text:
            return None
        
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
    print(f'Web Search: DDGS + Wikipedia fallback')
    print(f'Servers: {len(bot.guilds)}')
    print('=' * 50)

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    global VOICE_ENABLED
    content = message.content.strip() if message.content else ""
    
    # === COMMANDS ===
    if content == '!ping':
        await message.channel.send('🏓 Pong!')
        return
    
    if content == '!model':
        await message.channel.send(
            f'🤖 **Model:** `{MODEL_NAME}`\n'
            f'🌐 **Web Search:** DDGS + Wikipedia\n'
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
            await message.channel.send('🔍 *Searching...*')
            results = await search_web(query)
            if results and results.strip():
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
        embed.set_footer(text='Powered by Llama 3.3 + Web Search + Edge TTS')
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
                    if ai_reply and len(ai_reply) > 2000:
                        ai_reply = ai_reply[:1997] + '...'
                    await message.channel.send(ai_reply)
                    if VOICE_ENABLED and ai_reply:
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
            if ai_reply and len(ai_reply) > 2000:
                ai_reply = ai_reply[:1997] + '...'
            await message.channel.send(ai_reply)
            if VOICE_ENABLED and ai_reply:
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
