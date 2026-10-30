import speech_recognition as sr
import requests
import time
import re
import io

from scipy.io.wavfile import read
import sounddevice as sd
import os
import difflib
import subprocess

API_URL = "http://localhost:5000"
VOICEVOX_URL = "http://127.0.0.1:50021"
SPEAKER_ID = 1  # bisa ganti voice nanti
COOLDOWN = 1.5

res = requests.post(f"{API_URL}/api/sessions", json={})
session_id = res.json()["session_id"]

print("✅ Session ID:", session_id)

def speak(text):
    try:
        query = requests.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": SPEAKER_ID}
        ).json()

        audio = requests.post(
            f"{VOICEVOX_URL}/synthesis",
            params={"speaker": SPEAKER_ID},
            json=query
        )

        wav_bytes = io.BytesIO(audio.content)
        samplerate, data = read(wav_bytes)

        sd.play(data, samplerate)
        sd.wait()

    except Exception as e:
        print("❌ Error VOICEVOX:", e)

def split_text(text):
    parts = re.split(r'[.!?]', text)
    return [p.strip() for p in parts if p.strip()]


def speak_long(text):
    parts = split_text(text)

    for part in parts:
        speak(part)
        time.sleep(0.2)

def listen():
    r = sr.Recognizer()

    with sr.Microphone() as source:
        print("\n🎤 Ngomong sekarang...")
        r.adjust_for_ambient_noise(source, duration=0.5)
        audio = r.listen(source)

    try:
        text = r.recognize_google(audio, language="id-ID")
        print("📝 Lu bilang:", text)
        return text

    except sr.UnknownValueError:
        print("❌ Ga kedengeran")
        return None

    except sr.RequestError as e:
        print("❌ Error Speech API:", e)
        return None

def send_to_ai(message):
    try:
        res = requests.post(
            f"{API_URL}/api/chat/{session_id}",
            json={"message": message}
        )

        data = res.json()

        if "response" in data:
            response_text = data["response"]

            print("🤖 AI:", response_text)

            speak_long(response_text)

        else:
            print("❌ Error dari AI:", data)

    except Exception as e:
        print("❌ Gagal connect ke AI:", e)

if __name__ == "__main__":
    print("🚀 Voice Chat (VOICEVOX) Started!")

    while True:
        text = listen()

        if not text:
            continue

        send_to_ai(text)

        time.sleep(COOLDOWN)