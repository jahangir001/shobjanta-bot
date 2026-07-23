import discord
import os
import requests

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)

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
                'model': 'Llama 3.1 8B',
                'messages': [
                    {'role': 'system', 'content': f'You are ShobJanta AI, a helpful Discord assistant chatting with {username}. Be friendly, concise, and helpful. Keep responses under 2000 characters.'},
                    {'role': 'user', 'content': user_message}
                ],
                'max_tokens': 1000,
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

@bot.event
async def on_ready():
    print('==================================================')
    print(f'Bot ONLINE: {bot.user}')
    print(f'Servers: {len(bot.guilds)}')
    print('==================================================')

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    content = message.content.strip()
    
    # Help command
    if content == '!help':
        embed = discord.Embed(title='ShobJanta AI', description='AI-powered Discord assistant!', color=0x00ff00)
        embed.add_field(name='Commands', value='`!help` - Show this\n`!status` - Bot status\n`!ping` - Test bot', inline=False)
        await message.channel.send(embed=embed)
        return
    
    if content == '!status':
        latency = round(bot.latency * 1000)
        await message.channel.send(f'🟢 **Online!**\nLatency: {latency}ms\nServers: {len(bot.guilds)}')
        return
    
    if content == '!ping':
        await message.channel.send('🏓 Pong!')
        return
    
    # AI response to everything else
    async with message.channel.typing():
        reply = await get_ai_response(content, message.author.name)
        if len(reply) > 2000:
            reply = reply[:1997] + '...'
        await message.channel.send(reply)

# Run bot
bot.run(os.getenv("DISCORD_TOKEN"))
