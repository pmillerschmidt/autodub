import subprocess
import uuid
import os
import requests
from transformers import pipeline
from dotenv import load_dotenv

load_dotenv()


def dub_youtube_video(url, target_lang="es"):
    session_id = str(uuid.uuid4())
    os.makedirs("temp", exist_ok=True)

    audio_path = f"temp/{session_id}.m4a"
    video_path = f"temp/{session_id}.mp4"
    tts_path = f"temp/{session_id}_tts.mp3"
    output_path = f"temp/{session_id}_dub.mp4"

    print("▶️ Downloading video...")
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio[ext=m4a]", "-o", audio_path, url], check=True
    )
    subprocess.run(["yt-dlp", "-f", "bestvideo", "-o", video_path, url], check=True)
    print("✅ Download complete")

    print("📝 Transcribing...")
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
        transcript = transcript_json["results"]["channels"][0]["alternatives"][0].get(
            "transcript", ""
        )
    print("✅ Transcription complete")

    print("🌐 Translating...")
    translator = pipeline("translation", model=f"Helsinki-NLP/opus-mt-en-{target_lang}")
    translation = translator(transcript)[0]["translation_text"]
    print("✅ Translation complete")

    print("🗣️ Synthesizing speech...")
    eleven_api_key = os.getenv("ELEVENLABS_API_KEY")
    headers = {"xi-api-key": eleven_api_key}
    data = {
        "text": translation,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    r = requests.post(
        "https://api.elevenlabs.io/v1/text-to-speech/flHkNRp1BlvT73UL6gyz",
        json=data,
        headers=headers,
    )

    if (
        r.status_code != 200
        or r.headers.get("Content-Type", "").split(";")[0] != "audio/mpeg"
    ):
        return {
            "error": "TTS synthesis failed",
            "details": r.text,
            "status_code": r.status_code,
            "headers": dict(r.headers),
        }

    with open(tts_path, "wb") as f:
        f.write(r.content)

    print("✅ Speech synthesis complete")

    print("🎞️ Merging audio with video...")
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
    print(f"✅ Merge complete. Dubbed video saved to: {output_path}")


if __name__ == "__main__":
    # yt_link = input("Enter YouTube URL: ")
    # target_language = input("Enter target language code (e.g. es, fr, de): ").strip()
    yt_link = "https://www.youtube.com/watch?v=YJu6iJanLKU"
    target_language = "fr"
    dub_youtube_video(yt_link, target_language)
