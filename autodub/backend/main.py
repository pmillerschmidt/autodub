# backend/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import subprocess
import uuid
import os
import numpy as np
import requests
import librosa
import soundfile as sf
import tempfile
from transformers import pipeline
from pydub import AudioSegment
from dotenv import load_dotenv
import io
from collections import defaultdict

load_dotenv()

ELEVENLABS_VOICES = [
    os.getenv("ELEVENLABS_VOICE_1"),
    os.getenv("ELEVENLABS_VOICE_2"),
    os.getenv("ELEVENLABS_VOICE_3"),
]

VOICE_CACHE_DIR = "cloned_voices"
os.makedirs(VOICE_CACHE_DIR, exist_ok=True)

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
    clone_voice: bool = False
    keep_background: bool = False


def download_video(url, session_id):
    audio_path = f"temp/{session_id}.m4a"
    video_path = f"temp/{session_id}.mp4"
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio[ext=m4a]", "-o", audio_path, url], check=True
    )
    subprocess.run(["yt-dlp", "-f", "bestvideo", "-o", video_path, url], check=True)
    return audio_path, video_path


def extract_background(input_path: str):
    subprocess.run(
        ["demucs", "--two-stems", "vocals", "-o", "temp", input_path], check=True
    )
    song_name = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join("temp", "htdemucs", song_name, "no_vocals.wav")


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


def collect_speaker_audio(segments, audio_path):
    original_audio = AudioSegment.from_file(audio_path)
    speaker_audio = defaultdict(AudioSegment.silent)

    for speaker, group in segments:
        start_ms = int(float(group[0]["start"]) * 1000)
        end_ms = int(float(group[-1]["end"]) * 1000)
        segment_audio = original_audio[start_ms:end_ms]
        speaker_audio[speaker] += segment_audio

    for speaker, audio in speaker_audio.items():
        if len(audio) >= 1500:
            print(
                f"Speaker {speaker} total duration: {len(audio) / 1000.0:.2f} seconds"
            )
            path = os.path.join(VOICE_CACHE_DIR, f"{speaker}.mp3")
            audio.export(path, format="mp3")
            print(
                f"Saved audio for speaker {speaker} to {path}, size: {os.path.getsize(path)} bytes"
            )
        else:
            print(
                f"Skipping speaker {speaker}: audio too short ({len(audio)} ms) for cloning"
            )


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


def create_cloned_voice(speaker, voice_path, eleven_api_key):
    """Create a cloned voice using the working approach"""
    try:
        with open(voice_path, "rb") as audio_file:
            files = [
                (
                    "files",
                    (os.path.basename(voice_path), audio_file.read(), "audio/mpeg"),
                )
            ]

            data = {
                "name": f"cloned_{speaker}",
                "description": f"Cloned voice for speaker {speaker}",
            }

            response = requests.post(
                "https://api.elevenlabs.io/v1/voices/add",
                headers={"xi-api-key": eleven_api_key},
                files=files,
                data=data,
            )

        if response.status_code == 200:
            result = response.json()
            voice_id = result.get("voice_id")
            print(f"[SUCCESS] Voice cloned for speaker {speaker}: {voice_id}")
            return voice_id
        else:
            print(
                f"[ERROR] Voice cloning failed for speaker {speaker}: {response.status_code} - {response.text}"
            )
            return None

    except Exception as e:
        print(f"[ERROR] Exception during voice cloning for speaker {speaker}: {e}")
        return None


def translate_and_synthesize_segments(
    segments, target_lang, tts_path, clone_voice, speaker_clips=None
):
    translator = pipeline("translation", model=f"Helsinki-NLP/opus-mt-en-{target_lang}")
    eleven_api_key = os.getenv("ELEVENLABS_API_KEY")
    headers = {"xi-api-key": eleven_api_key}

    output_segments = []
    speaker_to_voice = {}
    voice_index = 0

    for i, (speaker, group) in enumerate(segments):
        text = " ".join([w["word"] for w in group])
        start_ms = int(float(group[0]["start"]) * 1000)
        end_ms = int(float(group[-1]["end"]) * 1000)
        segment_duration = end_ms - start_ms

        translated = translator(text)[0]["translation_text"]

        if clone_voice:
            voice_path = os.path.join(VOICE_CACHE_DIR, f"{speaker}.mp3")
            if speaker not in speaker_to_voice:
                if not os.path.exists(voice_path):
                    print(
                        f"Voice path does not exist for speaker {speaker}: {voice_path}"
                    )
                    # Use default voice if cloning file doesn't exist
                    speaker_to_voice[speaker] = ELEVENLABS_VOICES[
                        voice_index % len(ELEVENLABS_VOICES)
                    ]
                    voice_index += 1
                else:
                    # Use the working voice cloning approach
                    cloned_voice_id = create_cloned_voice(
                        speaker, voice_path, eleven_api_key
                    )
                    if cloned_voice_id:
                        speaker_to_voice[speaker] = cloned_voice_id
                        print(
                            f"Successfully cloned voice for speaker {speaker}: {cloned_voice_id}"
                        )
                    else:
                        print(
                            f"Voice cloning failed for speaker {speaker}, using default voice"
                        )
                        speaker_to_voice[speaker] = ELEVENLABS_VOICES[
                            voice_index % len(ELEVENLABS_VOICES)
                        ]
                        voice_index += 1
            voice_id = speaker_to_voice[speaker]
        else:
            if speaker not in speaker_to_voice:
                speaker_to_voice[speaker] = ELEVENLABS_VOICES[
                    voice_index % len(ELEVENLABS_VOICES)
                ]
                voice_index += 1
            voice_id = speaker_to_voice[speaker]

        endpoint = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        data = {
            "text": translated,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }

        r = requests.post(endpoint, json=data, headers=headers)
        if (
            r.status_code != 200
            or r.headers.get("Content-Type", "").split(";")[0] != "audio/mpeg"
        ):
            raise ValueError(f"TTS failed at segment {i}: {r.text}")

        segment_audio = AudioSegment.from_file(io.BytesIO(r.content), format="mp3")
        generated_duration = len(segment_audio)

        if generated_duration > segment_duration:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_in:
                segment_audio.export(temp_in.name, format="wav")
                y, sr = librosa.load(temp_in.name, sr=None)

            current_duration = librosa.get_duration(y=y, sr=sr)
            if current_duration > 0:
                stretch_ratio = current_duration / (segment_duration / 1000.0)
                y_stretched = librosa.effects.time_stretch(y, rate=stretch_ratio)
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".wav"
                ) as temp_out:
                    sf.write(temp_out.name, y_stretched, sr)
                    segment_audio = AudioSegment.from_file(temp_out.name, format="wav")

        output_segments.append((start_ms, segment_audio))

    final_audio = AudioSegment.silent(duration=0)
    current_position = 0

    for start_ms, segment_audio in output_segments:
        silence = AudioSegment.silent(duration=max(0, start_ms - current_position))
        final_audio += silence + segment_audio
        current_position = start_ms + len(segment_audio)

    final_audio.export(tts_path, format="mp3")


def merge_audio_video(video_path, tts_path, output_path, background_path=None):
    if background_path:
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                tts_path,
                "-i",
                background_path,
                "-filter_complex",
                "[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=3",
                "-c:a",
                "mp3",
                "-y",
                "temp/mixed_audio.mp3",
            ],
            check=True,
        )
        tts_path = "temp/mixed_audio.mp3"

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
    # init paths
    audio_path = f"temp/{session_id}.m4a"
    video_path = f"temp/{session_id}.mp4"
    tts_path = f"temp/{session_id}_tts.mp3"
    output_path = f"temp/{session_id}_dub.mp4"
    # init steps
    steps = []
    # download video
    audio_path, video_path = download_video(req.url, session_id)
    steps.append("Download complete")
    # transcribe audio
    words = transcribe_audio(audio_path)
    steps.append("Transcription complete")
    # group segments
    segments = group_segments(words)
    # collect speaker audio
    speaker_clips = (
        collect_speaker_audio(segments, audio_path) if req.clone_voice else None
    )
    # translate and synthesize segments
    translate_and_synthesize_segments(
        segments, req.target_lang, tts_path, req.clone_voice, speaker_clips
    )
    steps.append("Speech synthesis complete")
    # extract background
    background_path = extract_background(audio_path) if req.keep_background else None
    # merge audio and video
    merge_audio_video(video_path, tts_path, output_path, background_path)
    steps.append("Merge complete")

    return {"output_url": f"/temp/{session_id}_dub.mp4", "steps": steps}


app.mount("/temp", StaticFiles(directory="temp"), name="temp")
