# backend/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import subprocess
import uuid
import os
import requests
from transformers import pipeline
from dotenv import load_dotenv

load_dotenv()

VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DubRequest(BaseModel):
    url: str
    target_lang: str


def download_video(url, session_id):
    audio_path = f"temp/{session_id}.m4a"
    video_path = f"temp/{session_id}.mp4"
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio[ext=m4a]", "-o", audio_path, url], check=True
    )
    subprocess.run(["yt-dlp", "-f", "bestvideo", "-o", video_path, url], check=True)
    return audio_path, video_path


def transcribe_audio(audio_path):
    deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")
    with open(audio_path, "rb") as audio_file:
        headers = {
            "Authorization": f"Token {deepgram_api_key}",
            "Content-Type": "audio/m4a",
        }
        response = requests.post(
            "https://api.deepgram.com/v1/listen", headers=headers, data=audio_file
        )
        transcript_json = response.json()
        if "results" not in transcript_json:
            raise ValueError(f"Transcription failed: {transcript_json}")
        return transcript_json["results"]["channels"][0]["alternatives"][0].get(
            "transcript", ""
        )


def translate_text(text, target_lang):
    translator = pipeline("translation", model=f"Helsinki-NLP/opus-mt-en-{target_lang}")
    return translator(text)[0]["translation_text"]


def synthesize_speech(text, tts_path):
    eleven_api_key = os.getenv("ELEVENLABS_API_KEY")
    headers = {"xi-api-key": eleven_api_key}
    data = {
        "text": text,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
        json=data,
        headers=headers,
    )
    if (
        r.status_code != 200
        or r.headers.get("Content-Type", "").split(";")[0] != "audio/mpeg"
    ):
        raise ValueError(f"TTS synthesis failed: {r.text}")
    with open(tts_path, "wb") as f:
        f.write(r.content)


def merge_audio_video(video_path, tts_path, output_path):
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            video_path,
            "-i",
            tts_path,
            "-c:v",
            "copy",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            output_path,
        ],
        check=True,
    )


@app.post("/dub")
def dub_video(req: DubRequest):
    session_id = str(uuid.uuid4())
    os.makedirs("temp", exist_ok=True)

    audio_path = f"temp/{session_id}.m4a"
    video_path = f"temp/{session_id}.mp4"
    tts_path = f"temp/{session_id}_tts.mp3"
    output_path = f"temp/{session_id}_dub.mp4"

    steps = []

    # Step 1: Download
    audio_path, video_path = download_video(req.url, session_id)
    steps.append("Download complete")

    # Step 2: Transcribe
    transcript = transcribe_audio(audio_path)
    steps.append("Transcription complete")

    # Step 3: Translate
    translation = translate_text(transcript, req.target_lang)
    steps.append("Translation complete")

    # Step 4: TTS
    synthesize_speech(translation, tts_path)
    steps.append("Speech synthesis complete")

    # Step 5: Merge
    merge_audio_video(video_path, tts_path, output_path)
    steps.append("Merge complete")

    return {"output_url": f"/{output_path}", "steps": steps}


# Serve with uvicorn: uvicorn main:app --reload
app.mount("/temp", StaticFiles(directory="temp"), name="temp")
