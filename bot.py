import asyncio
from sqlite3 import connect
import discord
from discord.ext import commands
from utils import bytes_to_text, elevenlabs_text_to_audio, tanqr_react, load_audio
import json
import time
from io import BytesIO
from asyncio import Semaphore
from elevenlabs import play, save

OPENAI_KEY = None
ELEVELABS_KEY = None
voices = None
prompt = None
DISCORD_TOKEN = None

import whisper

with open('./config.json') as f:
    data = json.load(f)
    voices = data["elevenlabs"]["voices"]
    prompt = data["prompt"]
    confidence_min = data["confidence_min"]
    DISCORD_TOKEN = data["discord_token"]

intents = discord.Intents().default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# this is kind of a rough setup, for a more robust system use asyncio classes
connections = {}
queue = {}

async def acquire(id):
    if(not id in queue):
        queue[id] = Semaphore(1)
    await queue[id].acquire()

def release(id):
    queue[id].release()
    if(not queue[id].locked()):
        del queue[id]

@bot.command()
async def join(ctx):
    await acquire(ctx.guild.id)
    
    if(ctx.guild.id in connections.keys()):
        await ctx.send("already in a vc")
        release(ctx.guild.id)
        return
    
    voice = ctx.author.voice
    if not voice:
        await ctx.send("you aren't in a voice channel")
        release(ctx.guild.id)
        return

    vc = await voice.channel.connect()
    connections[ctx.guild.id] = [vc, ctx.channel, True]
    
    vc.start_recording(
        discord.sinks.WaveSink(),
        once_done,
        ctx.channel
    )

    async def periodic_delete(id):
        print("periodic started")
        await asyncio.sleep(30) #initial wait
        while id in connections:
            await acquire(id)
            
            if(id not in connections):
                print("periodic broken")
                break
            
            
            # connections[id][2] = False
            vc.stop_recording()
            
            # the vc will release the lock
            await asyncio.sleep(30)
            
            
    loop = asyncio.get_event_loop()
    task = loop.create_task(periodic_delete(ctx.guild.id))

    release(ctx.guild.id)

@bot.command()
async def respond(ctx):
    await acquire(ctx.guild.id)
    
    
    if ctx.guild.id in connections: 
        [vc, channel, out] = connections[ctx.guild.id]
        vc.stop_recording()
        # not releasing because all other actiosn have to be blocked till the once_done function finishes
    else:
        await ctx.send("not in a vc") 
        release(ctx.guild.id)

@bot.command()
async def leave(ctx):
    await acquire(ctx.guild.id)
    
    if ctx.guild.id in connections: 
        [vc, channel, out] = connections[ctx.guild.id]
        del connections[ctx.guild.id]
        await vc.disconnect()
        # once_done has to be finished so not releasing lock    
    else:
        await ctx.send("not in a vc") 
        release(ctx.guild.id)


async def once_done(sink: discord.sinks, channel: discord.TextChannel, *args):
    
    
    
    if(channel.guild.id not in connections):
        release(channel.guild.id)
        return
    
    vc = connections[channel.guild.id][0]
    out = connections[channel.guild.id][2]
    start_time = time.time()

    
    print(f'out: {out}')
    if out:
        segments_by_time = {}
        
        for user_id, file in sink.audio_data.items():
            bytes_audio = file.file.getbuffer().tobytes()
            user = bot.get_user(user_id)
            text_segments = bytes_to_text(bytes_audio)
            
            whisper_time = (time.time() - start_time)
            # limit file buffer to 1 mins somehow
            # file is discord.audiodata, file.file is _io.BytesIO
            
            
            for text in text_segments["segments"]:
                if(not text["confidence"] > confidence_min):
                    continue
                if(not text["start"] in segments_by_time):
                    segments_by_time[text["start"]] = []
                _t = text["text"]
                segments_by_time[text["start"]].append(f"{user} said {_t}")
            
        content = ""
        while segments_by_time and (len(content) < 100):
            segment_n = max(segments_by_time, key=segments_by_time.get)
            segments = segments_by_time[segment_n]
            for segment in segments:
                if(len(content) > 100):
                    break
                content = content + f"{segment}\n"
                
            del segments_by_time[segment_n]
        print(content)
        if(content.replace(" ", "").replace("\n", "")):
            content = "Respond to these people \n\n" + content
            response = tanqr_react(content, prompt)
                
            gpt_time = (time.time() - start_time)
            audio_response = elevenlabs_text_to_audio(response, voices["default"])
            elevenlabs_time = (time.time() - start_time)

            # demo of how iobase works
            # even playing file.file works, as it is of iobase class
            # for user_id, file in sink.audio_data.items():
            #     file = file.file.getbuffer().tobytes()
            #     # file = BytesIO(file)
            #     # vc.play(discord.FFmpegPCMAudio(file, pipe=True))
            #     play(file)
            
            # ffmpeg_obj = discord.FFmpegPCMAudio(BytesIO(audio_response), pipe=True)
            # vc.play(ffmpeg_obj)
            # this doesnt work
            # we cna play the discord sink files using this bytesio method
            # the elvenlabs play feature can play both audio_response and sink files - meaning they are the same format
            # yet the code refuse to work, so we just use tmp files

            save(audio_response, 'tmp.wav')
            vc.play(discord.FFmpegPCMAudio('tmp.wav'))
            
            print("--- %s seconds ---" % (time.time() - start_time))
        

    connections[channel.guild.id][2] = True
    vc.start_recording(
        discord.sinks.WaveSink(), 
        once_done,
        channel
    )
    
    release(channel.guild.id)

    
    




bot.run(DISCORD_TOKEN)