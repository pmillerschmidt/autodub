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
from pydub import AudioSegment
from dotenv import load_dotenv
import io
from collections import defaultdict

load_dotenv()

# Cycle through a list of predefined voices for different speakers
ELEVENLABS_VOICES = [
    os.getenv("ELEVENLABS_VOICE_1"),
    os.getenv("ELEVENLABS_VOICE_2"),
    os.getenv("ELEVENLABS_VOICE_3"),
]

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
            "https://api.deepgram.com/v1/listen?punctuate=true&utterances=false&paragraphs=false&diarize=true",
            headers=headers,
            data=audio_file,
        )
        transcript_json = response.json()
        if "results" not in transcript_json:
            raise ValueError(f"Transcription failed: {transcript_json}")
        words = transcript_json["results"]["channels"][0]["alternatives"][0].get(
            "words", []
        )
        return words


def group_segments(words):
    segments = []
    current_speaker = None
    current_segment = []

    for word in words:
        speaker = word.get("speaker", "unknown")
        if current_speaker is None:
            current_speaker = speaker

        if speaker == current_speaker:
            current_segment.append(word)
        else:
            if current_segment:
                segments.append((current_speaker, current_segment))
            current_segment = [word]
            current_speaker = speaker

    if current_segment:
        segments.append((current_speaker, current_segment))

    return segments


def translate_and_synthesize_segments(segments, target_lang, tts_path):
    translator = pipeline("translation", model=f"Helsinki-NLP/opus-mt-en-{target_lang}")
    eleven_api_key = os.getenv("ELEVENLABS_API_KEY")
    headers = {"xi-api-key": eleven_api_key}

    final_audio = AudioSegment.silent(duration=0)
    speaker_to_voice = {}
    voice_index = 0
    current_position = 0

    for i, (speaker, group) in enumerate(segments):
        if speaker not in speaker_to_voice:
            speaker_to_voice[speaker] = ELEVENLABS_VOICES[
                voice_index % len(ELEVENLABS_VOICES)
            ]
            voice_index += 1

        text = " ".join([w["word"] for w in group])
        start_ms = int(float(group[0]["start"]) * 1000)
        end_ms = int(float(group[-1]["end"]) * 1000)
        segment_duration = end_ms - start_ms

        translated = translator(text)[0]["translation_text"]

        voice_id = speaker_to_voice[speaker]
        data = {
            "text": translated,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            json=data,
            headers=headers,
        )
        if (
            r.status_code != 200
            or r.headers.get("Content-Type", "").split(";")[0] != "audio/mpeg"
        ):
            raise ValueError(f"TTS failed at segment {i}: {r.text}")

        segment_audio = AudioSegment.from_file(io.BytesIO(r.content), format="mp3")

        # Match duration: pad or trim to match original segment timing
        if len(segment_audio) < segment_duration:
            padding = AudioSegment.silent(
                duration=segment_duration - len(segment_audio)
            )
            segment_audio += padding
        else:
            segment_audio = segment_audio[:segment_duration]

        silence = AudioSegment.silent(duration=max(0, start_ms - current_position))
        final_audio += silence + segment_audio
        current_position = start_ms + len(segment_audio)

    final_audio.export(tts_path, format="mp3")


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

    audio_path, video_path = download_video(req.url, session_id)
    steps.append("Download complete")

    words = transcribe_audio(audio_path)
    steps.append("Transcription complete")

    segments = group_segments(words)
    translate_and_synthesize_segments(segments, req.target_lang, tts_path)
    steps.append("Speech synthesis complete")

    merge_audio_video(video_path, tts_path, output_path)
    steps.append("Merge complete")

    return {"output_url": f"/temp/{session_id}_dub.mp4", "steps": steps}


app.mount("/temp", StaticFiles(directory="temp"), name="temp")
