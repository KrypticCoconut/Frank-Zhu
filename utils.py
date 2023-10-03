import whisper_timestamped as whisper

import openai
import ffmpeg
import numpy as np
from elevenlabs import Voice, VoiceSettings, generate, set_api_key
import json

model = whisper.load_model("small", device="cuda")

with open('./config.json') as f:
    data = json.load(f)
    OPENAI_KEY = data["openai_api"]
    ELEVELABS_KEY = data["elevenlabs"]["api_key"]   
openai.api_key = OPENAI_KEY
set_api_key(ELEVELABS_KEY)


def load_audio(file, sr: int = 16000):
    
    if isinstance(file, bytes):
        inp = file
        file = 'pipe:'
    else:
        inp = None
    
    try:
        out, _ = (
            ffmpeg.input(file, threads=0)
            .output("-", format="s16le", acodec="pcm_s16le", ac=1, ar=sr)
            .run(cmd="ffmpeg", capture_stdout=True, capture_stderr=True, input=inp)
        )
    except ffmpeg.Error as e:
        raise RuntimeError(f"Failed to load audio: {e.stderr.decode()}") from e

    return np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0

def bytes_to_text(b):
    audio = load_audio(b)
    result = whisper.transcribe(model, audio, language="en")
    return result



def tanqr_react(content, prompt):
    response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[
        {
        "role": "system",
        "content": prompt
        },
        {
        "role": "user",
        "content": content
        }
    ],
    temperature=1,
    max_tokens=256,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0
    )
    return response.choices[0].message["content"]

def elevenlabs_text_to_audio(text, voice):
    audio = generate(
        text=text,
        voice=Voice(
            voice_id=voice,
            settings=VoiceSettings(stability=0.71, similarity_boost=0.5, style=0.0, use_speaker_boost=True)
        )
    )

    return audio



# discord memoryview -> bytes -> whisper -> text -> chatgpt -> text -> elevenlabs -> bytes -> discord ffmpeg