import requests
import sounddevice as sd
from scipy.io.wavfile import read
import io

VOICEVOX_URL = "http://127.0.0.1:50021"
SPEAKER_ID = 1 

def speak(text):
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