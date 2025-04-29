import discord
import aiohttp
import asyncio
import groq
import pathlib
import sqlite3
from google import genai  # Added for Google API
from google.genai import types
from PIL import Image
from io import BytesIO

# GroqCloud API Setup
client_groq = groq.Groq(api_key="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")

# Google Gemini API Setup [[1]][[6]]
API_KEY_GOOGLE = 'AIzaSyAiIOPDOcm9ZHbh8rdy1WM9X9shStD9W9M'
client_google = genai.Client(api_key=API_KEY_GOOGLE)

# Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Database initialization (unchanged) [[2]][[5]]
conn = sqlite3.connect('message_history.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        user_id TEXT,
        role TEXT,
        content TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()
conn.close()

# ... (existing helper functions: add_message, get_history, transcribe_audio, etc. remain unchanged)

@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    # Content filter (unchanged)
    filtered_words = ["nigga", "peyser", "gijd", "nigger", "gay", "seks", "sex", "porn", "fuck", "bitch"]
    if any(bad_word in message.content.lower() for bad_word in filtered_words):
        try:
            await message.delete()
        except Exception as e:
            print("Error deleting message: " + str(e))
        await message.channel.send(message.author.mention + " ⚠️ Shame on you! Please avoid using inappropriate language.")
        return

    # Handle audio attachments (unchanged)
    for attachment in message.attachments:
        if any(attachment.filename.lower().endswith(ext) for ext in [".mp3", ".m4a", ".wav", ".ogg"]):
            file_name = "audio_" + str(attachment.id) + ".mp3"
            file_path = pathlib.Path(file_name)
            await download_attachment(attachment.url, file_path)
            try:
                transcription_text = await asyncio.to_thread(transcribe_audio, file_path)
                await message.channel.send("Transcription: " + transcription_text)
            except Exception as e:
                await message.channel.send("Error transcribing audio: " + str(e))
            finally:
                if file_path.exists():
                    file_path.unlink()
            return

    # New /image command handler [[3]][[6]]
    if message.content.startswith('/image'):
        prompt = message.content[len('/image '):].strip()
        if not prompt:
            await message.channel.send("Please provide a prompt. Example: `/image a futuristic city`")
            return

        try:
            # Generate image via Google API
            response = await asyncio.to_thread(
                client_google.models.generate_content,
                model="gemini-2.0-flash-exp",
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=['IMAGE'])
            )

            # Extract image data
            image_data = None
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_data = part.inline_data.data
                    break

            if not image_data:
                raise ValueError("No image data received")

            # Send image to Discord
            image_file = discord.File(BytesIO(image_data), filename="generated_image.png")
            await message.channel.send(f"Here's your image for: '{prompt}'", file=image_file)

        except Exception as e:
            await message.channel.send(f"⚠️ Image generation failed: {str(e)}")
        return

    # Existing mention-based response logic (unchanged)
    if client.user not in message.mentions:
        return

    prompt = message.content.strip()
    if not prompt:
        return

    user_id = str(message.author.id)
    
    # Get message history from database
    history = await get_history(user_id)
    full_messages = history.copy()
    full_messages.append({"role": "user", "content": prompt})

    try:
        completion = client_groq.chat.completions.create(
            messages=full_messages,
            model="llama-3.3-70b-versatile",
        )
        response_text = completion.choices[0].message.content
        response_text += " " + message.author.mention
    except Exception as e:
        response_text = "Error fetching response: " + str(e)

    # Save both user message and response to database
    await add_message(user_id, 'user', prompt)
    await add_message(user_id, 'assistant', response_text)

    # Modified response sending logic
    if len(response_text) <= 2000:
        await message.channel.send(response_text)
    else:
        chunks = split_message(response_text)
        for chunk in chunks:
            await message.channel.send(chunk)
            await asyncio.sleep(0.5)  # Prevent rate limiting

    await client.process_commands(message)

client.run("discordbottoken")