# create_voice.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
AUDIO_PATH = "cloned_voices/0.mp3"
SPEAKER_NAME = "debug_speaker_0"

# Test script to create a voice using the ElevenLabs API


def create_voice(audio_path, speaker_name):
    """Create a cloned voice using ElevenLabs API"""
    if not os.path.exists(audio_path):
        print(f"[ERROR] File does not exist: {audio_path}")
        return None

    file_size = os.path.getsize(audio_path)
    print(f"[INFO] Audio file found: {audio_path} ({file_size} bytes)")

    try:
        with open(audio_path, "rb") as audio_file:
            files = [
                (
                    "files",
                    (os.path.basename(audio_path), audio_file.read(), "audio/mpeg"),
                )
            ]

            data = {"name": speaker_name, "description": "Voice cloned via API"}

            response = requests.post(
                "https://api.elevenlabs.io/v1/voices/add",
                headers={"xi-api-key": ELEVENLABS_API_KEY},
                files=files,
                data=data,
            )

        if response.status_code == 200:
            result = response.json()
            print(f"[SUCCESS] Voice created: {result}")
            return result
        else:
            print(
                f"[FAILURE] Status: {response.status_code}, Response: {response.text}"
            )
            return None

    except Exception as e:
        print(f"[ERROR] Voice creation failed: {e}")
        return None


if __name__ == "__main__":
    result = create_voice(AUDIO_PATH, SPEAKER_NAME)
    if result:
        voice_id = result.get("voice_id")
        requires_verification = result.get("requires_verification", False)

        print(f"[INFO] Voice ID: {voice_id}")
        print(f"[INFO] Requires verification: {requires_verification}")

        if not requires_verification:
            print("[INFO] Voice is ready to use!")
        else:
            print("[INFO] Voice requires verification before use.")
    else:
        print("[ERROR] Voice creation failed")
