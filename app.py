from flask import Flask, request, jsonify, redirect, send_from_directory
from flask_cors import CORS
from config import Config
from memory.memory_manager import MemoryManager
from ai_modules.openai_ai import generate_response as generate_openai_response
from ai_modules.gemini_ai import generate_response as ,
DEFAULT_AI_PROVIDER = "gemini"
SUPPORTED_AI_PROVIDERS = {"openai", "gemini"}

from spotipy.oauth2 import SpotifyOAuth
import spotipy

from dotenv import load_dotenv

from difflib import SequenceMatcher

import time
import requests
import os
import re

from datetime import datetime
from todo_api import todo_bp

# =========================================================
# LOCAL OFFLINE JP -> ID TRANSLATOR
# Model: facebook/nllb-200-distilled-600M
#
# First run downloads the model once.
# After it is cached, translation runs locally/offline.
#
# Install:
# pip install torch transformers sentencepiece
# =========================================================

import torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

LOCAL_TRANSLATION_MODEL = "facebook/nllb-200-distilled-600M"
LOCAL_TRANSLATION_SOURCE = "jpn_Jpan"
LOCAL_TRANSLATION_TARGET = "ind_Latn"

local_translation_tokenizer = None
local_translation_model = None
local_translation_device = None

# =========================================================
# LOAD ENV
# =========================================================

load_dotenv()


# =========================================================
# FLASK
# =========================================================

app = Flask(
    __name__,
    static_folder='.',
    static_url_path=''
)

app.register_blueprint(
    todo_bp
)

CORS(app)


# =========================================================
# CONFIG
# =========================================================

config = Config()

memory_manager = MemoryManager(
    config.MEMORY_DB_PATH
)


# =========================================================
# REQUEST COOLDOWN
# =========================================================

last_request_time = {}

COOLDOWN = 5


# =========================================================
# VOICEVOX
# =========================================================

VOICEVOX_URL = "http://127.0.0.1:50021"


# =========================================================
# BASE DIRECTORY
# =========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


# =========================================================
# MEMORY FILE
# =========================================================

MEMORY_FILE = os.path.join(
    BASE_DIR,
    "memory.txt"
)


# =========================================================
# LOCAL SONGS
# =========================================================

SONGS_FOLDER = os.path.join(
    BASE_DIR,
    "songs"
)

SUPPORTED_AUDIO = (
    ".mp3",
    ".wav",
    ".ogg",
    ".m4a",
    ".flac",
    ".aac",
    ".webm"
)


# =========================================================
# SPOTIFY CONFIG
# =========================================================

SPOTIFY_CLIENT_ID = os.getenv(
    "SPOTIFY_CLIENT_ID"
)

SPOTIFY_CLIENT_SECRET = os.getenv(
    "SPOTIFY_CLIENT_SECRET"
)

SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI"
)


SPOTIFY_SCOPE = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing"
)


spotify_oauth = SpotifyOAuth(

    client_id=SPOTIFY_CLIENT_ID,

    client_secret=SPOTIFY_CLIENT_SECRET,

    redirect_uri=SPOTIFY_REDIRECT_URI,

    scope=SPOTIFY_SCOPE,

    cache_path=".spotify_cache",

    open_browser=False
)


# =========================================================
# SPOTIFY CONNECTION
# =========================================================

def get_spotify():

    try:

        cached_token = (
            spotify_oauth
            .cache_handler
            .get_cached_token()
        )

        if not cached_token:
            return None

        token_info = (
            spotify_oauth
            .validate_token(
                cached_token
            )
        )

        if not token_info:
            return None

        return spotipy.Spotify(
            auth=token_info[
                "access_token"
            ]
        )

    except Exception as e:

        print(
            "SPOTIFY AUTH ERROR:",
            e
        )

        return None


# =========================================================
# DETECT SONG COMMAND
# =========================================================

def detect_song_command(text):

    text = text.lower().strip()

    keywords = [

        "putar lagu ",
        "putarkan lagu ",
        "putar ",

        "play lagu ",
        "play ",

        "mainkan lagu ",
        "mainkan ",

        "buka lagu ",
        "buka musik ",

        "putar musik ",
        "putarkan musik "
    ]

    for keyword in keywords:

        if text.startswith(keyword):

            song_name = text[
                len(keyword):
            ].strip()

            if song_name:
                return song_name

    return None


# =========================================================
# DETECT ANIME COMMAND
# =========================================================

def detect_anime_command(text):

    text = text.lower().strip()

    anime_keywords = [
        "buka anime ",
        "bukain anime ",
        "cari anime ",
        "carikan anime ",
        "search anime ",
        "open anime ",
        "coba buka anime ",
        "coba search anime ",
        "coba cari anime "
    ]

    for keyword in anime_keywords:
        if text.startswith(keyword):
            anime_name = text[len(keyword):].strip()
            if anime_name:
                return anime_name

    return None


# =========================================================
# STOP COMMAND
# =========================================================

def is_stop_command(text):

    text = text.lower().strip()

    stop_keywords = [

        "stop",
        "stop lagu",
        "stop lagunya",
        "stop musik",
        "stop musiknya",

        "hentikan",
        "hentikan lagu",
        "hentikan lagunya",
        "hentikan musik",

        "berhenti",
        "berhenti lagu",
        "berhenti musik"
    ]

    return text in stop_keywords


# =========================================================
# PAUSE COMMAND
# =========================================================

def is_pause_command(text):

    text = text.lower().strip()

    pause_keywords = [

        "pause",
        "pause lagu",
        "pause lagunya",
        "pause musik",

        "jeda",
        "jeda lagu",
        "jeda lagunya",
        "jeda musik"
    ]

    return text in pause_keywords


# =========================================================
# NORMALIZE LOCAL SONG NAME
# =========================================================

def normalize_song_name(name):

    name = os.path.splitext(
        name
    )[0]

    name = name.lower()

    name = re.sub(
        r"[^a-z0-9\s]",
        " ",
        name
    )

    name = re.sub(
        r"\s+",
        " ",
        name
    )

    return name.strip()


# =========================================================
# FIND LOCAL SONG
# =========================================================

def find_local_song(song_name):

    if not os.path.exists(
        SONGS_FOLDER
    ):

        print(
            "SONGS FOLDER NOT FOUND:",
            SONGS_FOLDER
        )

        return None


    query = normalize_song_name(
        song_name
    )

    best_file = None
    best_score = 0


    for filename in os.listdir(
        SONGS_FOLDER
    ):

        file_path = os.path.join(
            SONGS_FOLDER,
            filename
        )

        if not os.path.isfile(
            file_path
        ):
            continue


        if not filename.lower().endswith(
            SUPPORTED_AUDIO
        ):
            continue


        local_name = normalize_song_name(
            filename
        )


        # =========================
        # EXACT MATCH
        # =========================

        if query == local_name:

            print(
                "LOCAL EXACT MATCH:",
                filename
            )

            return filename


        # =========================
        # QUERY ADA DI NAMA FILE
        # =========================

        if query in local_name:

            score = 0.95


        # =========================
        # NAMA FILE ADA DI QUERY
        # =========================

        elif local_name in query:

            score = 0.90


        # =========================
        # FUZZY MATCH
        # =========================

        else:

            score = SequenceMatcher(
                None,
                query,
                local_name
            ).ratio()


        if score > best_score:

            best_score = score
            best_file = filename


    print(
        "BEST LOCAL SONG:",
        best_file,
        "SCORE:",
        best_score
    )


    if best_score >= 0.60:

        return best_file


    return None


# =========================================================
# SPOTIFY SEARCH AND PLAY
# =========================================================

def spotify_search_and_play(song_name):

    spotify = get_spotify()


    if not spotify:

        return {

            "response":
                "JP: Spotifyが接続されていません\n"
                "ID: Spotify belum terhubung",

            "type":
                "spotify_auth",

            "status":
                "auth_required",

            "login_url":
                "/api/spotify/login"
        }


    try:

        results = spotify.search(

            q=song_name,

            type="track",

            limit=1
        )


        tracks = (
            results
            .get(
                "tracks",
                {}
            )
            .get(
                "items",
                []
            )
        )


        if not tracks:

            return {

                "response": (
                    f"JP: {song_name}という曲は見つかりません\n"
                    f"ID: Lagu {song_name} belum ditemukan"
                ),

                "type":
                    "spotify_not_found",

                "status":
                    "not_found"
            }


        track = tracks[0]


        track_name = track[
            "name"
        ]


        artist_name = ", ".join(

            artist["name"]

            for artist in track[
                "artists"
            ]
        )


        track_uri = track[
            "uri"
        ]


        devices = spotify.devices()


        if not devices.get(
            "devices"
        ):

            return {

                "response": (
                    "JP: Spotifyのデバイスが見つかりません\n"
                    "ID: Perangkat Spotify tidak ditemukan"
                ),

                "type":
                    "spotify_no_device",

                "status":
                    "no_device"
            }


        active_device = None


        for device in devices[
            "devices"
        ]:

            if device.get(
                "is_active"
            ):

                active_device = device

                break


        if active_device is None:

            active_device = (
                devices[
                    "devices"
                ][0]
            )


        device_id = active_device[
            "id"
        ]


        spotify.start_playback(

            device_id=device_id,

            uris=[
                track_uri
            ]
        )


        return {

            "response": (
                f"JP: {track_name}をSpotifyから再生します\n"
                f"ID: Memutar {track_name} dari Spotify"
            ),

            "type":
                "spotify",

            "source":
                "spotify",

            "action":
                "play",

            "status":
                "success",

            "song":
                track_name,

            "artist":
                artist_name,

            "uri":
                track_uri
        }


    except spotipy.exceptions.SpotifyException as e:

        print(
            "SPOTIFY ERROR:",
            e
        )

        return {

            "response": (
                "JP: Spotifyで曲を再生できません\n"
                "ID: Spotify gagal memutar lagu"
            ),

            "type":
                "spotify_error",

            "action":
                "none",

            "status":
                "error"
        }


    except Exception as e:

        print(
            "SPOTIFY ERROR:",
            e
        )

        return {

            "response": (
                "JP: Spotifyで問題が発生しました\n"
                "ID: Terjadi masalah pada Spotify"
            ),

            "type":
                "spotify_error",

            "action":
                "none",

            "status":
                "error"
        }


# =========================================================
# LOCAL FIRST THEN SPOTIFY
# =========================================================

def play_song(song_name):

    print(
        "================================="
    )

    print(
        "SONG REQUEST:",
        song_name
    )


    # =========================
    # 1. CHECK LOCAL
    # =========================

    local_song = find_local_song(
        song_name
    )


    if local_song:

        print(
            "LOCAL SONG FOUND:",
            local_song
        )


        song_title = os.path.splitext(
            local_song
        )[0]


        return {

            "response": (
                f"JP: {song_title}をローカルから再生します\n"
                f"ID: Memutar {song_title} dari penyimpanan lokal"
            ),

            "type":
                "local_song",

            "source":
                "local",

            "action":
                "play",

            "status":
                "success",

            "song":
                song_title,

            "filename":
                local_song,

            "audio_url":
                "/songs/" + local_song
        }


    # =========================
    # 2. FALLBACK SPOTIFY
    # =========================

    print(
        "LOCAL SONG NOT FOUND"
    )

    print(
        "FALLBACK TO SPOTIFY:",
        song_name
    )


    return spotify_search_and_play(
        song_name
    )


# =========================================================
# SPOTIFY STOP
# =========================================================

def spotify_stop():

    spotify = get_spotify()


    if not spotify:

        return {

            "response": (
                "JP: Spotifyが接続されていません\n"
                "ID: Spotify belum terhubung"
            ),

            "type":
                "spotify_auth",

            "action":
                "none",

            "status":
                "auth_required",

            "login_url":
                "/api/spotify/login"
        }


    try:

        spotify.pause_playback()


        return {

            "response": (
                "JP: 曲を停止します\n"
                "ID: Lagu dihentikan"
            ),

            "type":
                "spotify",

            "action":
                "stop",

            "status":
                "success"
        }


    except Exception as e:

        print(
            "SPOTIFY STOP ERROR:",
            e
        )


        return {

            "response": (
                "JP: 曲を停止できません\n"
                "ID: Lagu tidak dapat dihentikan"
            ),

            "type":
                "spotify_error",

            "action":
                "stop",

            "status":
                "error"
        }


# =========================================================
# SPOTIFY PAUSE
# =========================================================

def spotify_pause():

    spotify = get_spotify()


    if not spotify:

        return {

            "response": (
                "JP: Spotifyが接続されていません\n"
                "ID: Spotify belum terhubung"
            ),

            "type":
                "spotify_auth",

            "action":
                "pause",

            "status":
                "auth_required"
        }


    try:

        spotify.pause_playback()


        return {

            "response": (
                "JP: 曲を一時停止します\n"
                "ID: Lagu dijeda"
            ),

            "type":
                "spotify",

            "action":
                "pause",

            "status":
                "success"
        }


    except Exception as e:

        print(
            "SPOTIFY PAUSE ERROR:",
            e
        )


        return {

            "response": (
                "JP: 曲を一時停止できません\n"
                "ID: Lagu tidak dapat dijeda"
            ),

            "type":
                "spotify_error",

            "action":
                "pause",

            "status":
                "error"
        }


# =========================================================
# CONVERT HISTORY
# =========================================================

def convert_history(raw_history):

    formatted = []


    for msg in raw_history:

        role = (
            "user"
            if msg["role"] == "user"
            else "model"
        )


        if not msg.get(
            "content"
        ):

            continue


        formatted.append({

            "role":
                role,

            "parts": [

                {
                    "text":
                        msg[
                            "content"
                        ]
                }

            ]
        })


    return formatted


# =========================================================
# MEMORY FUNCTIONS
# =========================================================

def ensure_memory_file():

    if not os.path.exists(
        MEMORY_FILE
    ):

        with open(
            MEMORY_FILE,
            "w",
            encoding="utf-8"
        ):
            pass


def read_memories():

    ensure_memory_file()


    with open(
        MEMORY_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return [

            line.strip()

            for line in file

            if line.strip()

        ]


def save_memory(memory_text):

    ensure_memory_file()


    with open(
        MEMORY_FILE,
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            memory_text.strip()
            +
            "\n"
        )


def delete_memory(memory_text):

    memories = read_memories()

    target = (
        memory_text
        .strip()
        .lower()
    )


    remaining = [

        memory

        for memory in memories

        if (
            memory
            .strip()
            .lower()
            != target
        )
    ]


    with open(
        MEMORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        for memory in remaining:

            file.write(
                memory + "\n"
            )


    return (
        len(memories)
        !=
        len(remaining)
    )


def get_today_memories():

    today = datetime.now().strftime(
        "%d/%m/%Y"
    )

    memories = read_memories()


    return [

        memory

        for memory in memories

        if memory.startswith(
            "[MEMORY] "
            +
            today
            +
            "|"
        )
    ]


def get_memories_by_date(
    date_text
):

    memories = read_memories()


    return [

        memory

        for memory in memories

        if memory.startswith(
            "[MEMORY] "
            +
            date_text
            +
            "|"
        )
    ]


# =========================================================
# JP -> INDONESIAN TRANSLATION
# =========================================================

def extract_japanese_response(text):

    text = str(text or "").strip()

    if not text:
        return ""

    # Jika model masih mengirim JP: ambil isi JP saja.
    match = re.search(
        r"JP\s*:\s*([\s\S]*?)(?=\n?\s*ID\s*:|$)",
        text,
        flags=re.IGNORECASE
    )

    if match:
        return match.group(1).strip()

    # Fallback: buang label ID lama jika model melanggar prompt.
    text = re.sub(
        r"\n?\s*ID\s*:[\s\S]*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    return text.strip()


def load_local_translation_model():

    global local_translation_tokenizer
    global local_translation_model
    global local_translation_device

    if (
        local_translation_tokenizer is not None
        and
        local_translation_model is not None
    ):
        return

    print(
        "🌐 Loading local JP -> ID translator..."
    )

    # CUDA jika tersedia, selain itu CPU.
    local_translation_device = (
        torch.device("cuda")
        if torch.cuda.is_available()
        else torch.device("cpu")
    )

    local_translation_tokenizer = (
        AutoTokenizer.from_pretrained(
            LOCAL_TRANSLATION_MODEL,
            src_lang=LOCAL_TRANSLATION_SOURCE
        )
    )

    local_translation_model = (
        AutoModelForSeq2SeqLM.from_pretrained(
            LOCAL_TRANSLATION_MODEL
        )
    )

    local_translation_model.to(
        local_translation_device
    )

    local_translation_model.eval()

    print(
        "✅ Local translator ready on",
        local_translation_device
    )


def translate_japanese_to_indonesian(japanese_text):

    japanese_text = str(
        japanese_text or ""
    ).strip()

    if not japanese_text:
        return ""

    try:

        load_local_translation_model()

        # Pastikan source language tetap Japanese.
        local_translation_tokenizer.src_lang = (
            LOCAL_TRANSLATION_SOURCE
        )

        inputs = local_translation_tokenizer(
            japanese_text,
            return_tensors="pt",
            truncation=True,
            max_length=512
        )

        inputs = {
            key: value.to(
                local_translation_device
            )
            for key, value in inputs.items()
        }

        target_token_id = (
            local_translation_tokenizer
            .convert_tokens_to_ids(
                LOCAL_TRANSLATION_TARGET
            )
        )

        with torch.inference_mode():

            generated_tokens = (
                local_translation_model.generate(
                    **inputs,
                    forced_bos_token_id=
                        target_token_id,
                    max_new_tokens=256,
                    num_beams=4,
                    early_stopping=True
                )
            )

        translated = (
            local_translation_tokenizer
            .batch_decode(
                generated_tokens,
                skip_special_tokens=True
            )[0]
            .strip()
        )

        if (
            translated
            and
            translated != japanese_text
        ):

            print(
                "LOCAL JP -> ID:",
                japanese_text,
                "->",
                translated
            )

            return translated

        print(
            "LOCAL TRANSLATOR OUTPUT INVALID:",
            translated
        )

    except Exception as e:

        print(
            "LOCAL JP -> ID ERROR:",
            type(e).__name__,
            repr(e)
        )

    return (
        "Terjemahan Indonesia sementara tidak tersedia"
    )


def build_bilingual_response(ai_text):

    jp_text = extract_japanese_response(
        ai_text
    )

    if not jp_text:
        jp_text = "わかりません"

    id_text = translate_japanese_to_indonesian(
        jp_text
    )

    return (
        f"JP: {jp_text}\n"
        f"ID: {id_text}"
    )


# =========================================================
# PROCESS MEMORY OUTPUT
# =========================================================

def process_memory_output(
    ai_response
):

    lines = ai_response.splitlines()

    normal_lines = []

    memory_actions = []


    for line in lines:

        line = line.strip()


        if line.startswith(
            "[MEMORY]"
        ):

            memory_text = line[
                len("[MEMORY]"):
            ].strip()


            if memory_text:

                save_memory(
                    "[MEMORY] "
                    +
                    memory_text
                )


            memory_actions.append(
                "Memory disimpan"
            )


        elif line.startswith(
            "[DELETE_MEMORY]"
        ):

            memory_text = line[
                len(
                    "[DELETE_MEMORY]"
                ):
            ].strip()


            if memory_text:

                deleted = delete_memory(
                    "[MEMORY] "
                    +
                    memory_text
                )


                if deleted:

                    memory_actions.append(
                        "Memory dihapus"
                    )


        else:

            normal_lines.append(
                line
            )


    return (

        "\n".join(

            line

            for line in normal_lines

            if line

        ).strip(),

        memory_actions
    )


# =========================================================
# INDEX
# =========================================================

@app.route('/')
def index():

    return app.send_static_file(
        'index.html'
    )


# =========================================================
# SERVE LOCAL SONG
# =========================================================

@app.route(
    "/songs/<path:filename>"
)
def serve_song(filename):

    return send_from_directory(
        SONGS_FOLDER,
        filename
    )


# =========================================================
# SPOTIFY LOGIN
# =========================================================

@app.route(
    '/api/spotify/login'
)
def spotify_login():


    if (
        not SPOTIFY_CLIENT_ID
        or
        not SPOTIFY_CLIENT_SECRET
    ):

        return jsonify({

            "error":
                "SPOTIFY_CLIENT_ID atau SPOTIFY_CLIENT_SECRET belum diatur"

        }), 500


    auth_url = (
        spotify_oauth
        .get_authorize_url()
    )


    return redirect(
        auth_url
    )


# =========================================================
# SPOTIFY CALLBACK
# =========================================================

@app.route(
    '/api/spotify/callback'
)
def spotify_callback():


    try:

        code = request.args.get(
            "code"
        )


        if not code:

            return jsonify({

                "error":
                    "Kode Spotify tidak ditemukan"

            }), 400


        token_info = (
            spotify_oauth
            .get_access_token(
                code,
                as_dict=True
            )
        )


        if not token_info:

            return jsonify({

                "error":
                    "Gagal mendapatkan token Spotify"

            }), 500


        return """
        <html>

        <head>

            <title>
                Spotify Connected
            </title>

        </head>

        <body
            style="
                font-family:Arial;
                text-align:center;
                padding-top:100px;
            "
        >

            <h1>
                Spotify berhasil terhubung
            </h1>

            <p>
                Kamu bisa kembali ke JayDream AI.
            </p>

        </body>

        </html>
        """


    except Exception as e:

        print(
            "SPOTIFY CALLBACK ERROR:",
            e
        )


        return jsonify({

            "error":
                str(e)

        }), 500


# =========================================================
# SPOTIFY STATUS
# =========================================================

@app.route(
    '/api/spotify/status'
)
def spotify_status():


    spotify = get_spotify()


    if not spotify:

        return jsonify({
            "connected":
                False
        })


    try:

        user = spotify.current_user()


        return jsonify({

            "connected":
                True,

            "user":
                user.get(
                    "display_name"
                ),

            "id":
                user.get(
                    "id"
                )

        })


    except Exception as e:

        print(
            "SPOTIFY STATUS ERROR:",
            e
        )


        return jsonify({

            "connected":
                False

        })


# =========================================================
# SPOTIFY DEVICES
# =========================================================

@app.route(
    '/api/spotify/devices'
)
def spotify_devices():


    spotify = get_spotify()


    if not spotify:

        return jsonify({

            "error":
                "Spotify belum terhubung"

        }), 401


    try:

        devices = spotify.devices()


        return jsonify({

            "devices":
                devices.get(
                    "devices",
                    []
                )

        })


    except Exception as e:

        return jsonify({

            "error":
                str(e)

        }), 500


# =========================================================
# CREATE SESSION
# =========================================================

@app.route(
    '/api/sessions',
    methods=['POST']
)
def create_session():


    data = request.get_json(
        silent=True
    ) or {}


    personality = data.get(

        'personality',

        config.PERSONALITY_TEMPLATES[
            'default'
        ]
    )


    session_id = (
        memory_manager
        .create_session(
            personality
        )
    )


    return jsonify({

        'session_id':
            session_id,

        'personality':
            personality

    }), 201


# =========================================================
# TTS
# =========================================================

@app.route(
    "/api/tts",
    methods=["POST"]
)
def tts():


    try:

        data = request.get_json(
            silent=True
        ) or {}


        text = data.get(
            "text",
            ""
        ).strip()


        speaker = data.get(
            "speaker",
            3
        )


        if not text:

            return jsonify({

                "error":
                    "Text kosong"

            }), 400


        query = requests.post(

            f"{VOICEVOX_URL}/audio_query",

            params={

                "text":
                    text,

                "speaker":
                    speaker
            },

            timeout=15
        )


        query.raise_for_status()


        audio = requests.post(

            f"{VOICEVOX_URL}/synthesis",

            params={

                "speaker":
                    speaker
            },

            json=query.json(),

            timeout=30
        )


        audio.raise_for_status()


        return audio.content, 200, {

            "Content-Type":
                "audio/wav"

        }


    except Exception as e:

        print(
            "VOICEVOX ERROR:",
            e
        )


        return jsonify({

            "error":
                str(e)

        }), 500


# =========================================================
# CHAT
# =========================================================

@app.route(
    '/api/chat/<session_id>',
    methods=['POST']
)
def chat(session_id):


    data = request.get_json(
        silent=True
    ) or {}


    user_message = data.get(
        "message",
        ""
    ).strip()

    # =====================================================
    # AI PROVIDER
    # =====================================================

    provider = str(
        data.get(
            "provider",
            DEFAULT_AI_PROVIDER
        )
    ).strip().lower()


    if provider not in SUPPORTED_AI_PROVIDERS:

        return jsonify({

            "error":
                f"Provider AI tidak valid: {provider}"

        }), 400


    # =====================================================
    # OUTPUT TOKEN LIMITER
    # =====================================================

    try:

        max_output_tokens = int(

            data.get(
                "max_output_tokens",
                300
            )

        )

    except (
        TypeError,
        ValueError
    ):

        max_output_tokens = 300


    # Minimum 50 token
    # Maximum 2000 token

    max_output_tokens = max(

        50,

        min(
            max_output_tokens,
            2000
        )

    )


    print(
        "🎯 OUTPUT TOKEN LIMIT:",
        max_output_tokens
    )


    # =====================================================
    # MEMORY POWER / HISTORY LIMITER
    # =====================================================

    try:
        memory_power = int(
            data.get(
                "memory_power",
                15
            )
        )
    except (TypeError, ValueError):
        memory_power = 15

    memory_power = max(
        1,
        min(memory_power, 30)
    )

    print(
        "🧠 MEMORY POWER:",
        memory_power
    )


    # =====================================================
    # VALIDATE MESSAGE
    # =====================================================

    if not user_message:

        return jsonify({

            "error":
                "Message kosong!"

        }), 400


    # =====================================================
    # ANIME COMMAND
    # =====================================================

    anime_name = detect_anime_command(
        user_message
    )

    if anime_name:

        print(
            "🎬 ANIME REQUEST:",
            anime_name
        )

        memory_manager.save_message(
            session_id,
            "user",
            user_message
        )

        anime_response = (
            f"JP: {anime_name}を検索します\n"
            f"ID: Mencari anime {anime_name}"
        )

        memory_manager.save_message(
            session_id,
            "model",
            anime_response
        )

        return jsonify({
            "response": anime_response,
            "type": "anime_search",
            "action": "open",
            "status": "success",
            "anime": anime_name,
            "session_id": session_id
        })


    # =====================================================
    # STOP COMMAND
    # =====================================================

    if is_stop_command(
        user_message
    ):

        print(
            "STOP REQUEST"
        )


        result = spotify_stop()


        result[
            "session_id"
        ] = session_id


        return jsonify(
            result
        )


    # =====================================================
    # PAUSE COMMAND
    # =====================================================

    if is_pause_command(
        user_message
    ):

        print(
            "PAUSE REQUEST"
        )


        result = spotify_pause()


        result[
            "session_id"
        ] = session_id


        return jsonify(
            result
        )


    # =====================================================
    # SONG COMMAND
    # =====================================================

    song_name = detect_song_command(
        user_message
    )


    if song_name:

        print(
            "PLAY REQUEST:",
            song_name
        )


        result = play_song(
            song_name
        )


        result[
            "session_id"
        ] = session_id


        return jsonify(
            result
        )


    # =====================================================
    # NORMAL AI CHAT
    # =====================================================

    session = (
        memory_manager
        .get_session(
            session_id
        )
    )


    if not session:

        return jsonify({

            "error":
                "Session tidak ditemukan!"

        }), 404


    now = time.time()


    if session_id in last_request_time:

        elapsed = (
            now
            -
            last_request_time[
                session_id
            ]
        )


        if elapsed < COOLDOWN:

            sisa = max(

                1,

                int(
                    COOLDOWN
                    -
                    elapsed
                )
            )


            return jsonify({

                "error":
                    f"Tunggu {sisa} detik lagi"

            }), 429


    last_request_time[
        session_id
    ] = now


    # History lengkap tetap tersimpan di database untuk UI
    full_history = (
        memory_manager
        .get_conversation_history(
            session_id
        )
    )

    # Hanya pesan USER yang diteruskan kembali ke model
    # Jawaban AI sebelumnya tidak ikut menjadi input token
    all_user_history = [
        msg
        for msg in full_history
        if msg.get("role") == "user"
    ]

    # MEMORY POWER menentukan jumlah pesan USER lama
    # yang dikirim kembali ke OpenAI/Gemini.
    # Database/UI tetap menyimpan history lengkap.
    raw_history = all_user_history[-memory_power:]

    print(
        "🧠 HISTORY SENT:",
        len(raw_history),
        "/",
        len(all_user_history),
        "previous user messages"
    )


    history = convert_history(
        raw_history
    )


    today_memories = (
        get_today_memories()
    )


    memory_context = ""


    if today_memories:

        memory_context = (

            "\n\nMemory hari ini:\n"

            +

            "\n".join(
                today_memories
            )
        )


    try:

        system_instruction = f"""
{session['personality']}

Jawab HANYA dalam bahasa Jepang.

Gunakan huruf Jepang yang sesuai.

Jangan menerjemahkan jawaban ke Bahasa Indonesia.
Jangan membuat bagian ID.
Jangan menulis label JP kecuali diperlukan oleh sistem.
Jangan gunakan tanda baca.
Jangan gunakan emoji.
Gunakan bahasa singkat padat dan jelas.

Untuk jawaban chat biasa keluarkan hanya teks bahasa Jepang.

Kamu adalah AI dalam sebuah web.

Anggap kamu dibuat oleh Jaiden Zhang.

Kamu adalah AI yang lucu selalu membantu dan jarang menurut
tapi kadang baik.

Kamu memiliki sistem memory.

Jika user meminta sesuatu untuk diingat,
buat SATU baris dengan format:

[MEMORY] DD/MM/YYYY|HH:MM|WIB|KEGIATAN

Contoh:

[MEMORY] 17/08/2026|08:00|WIB|Kegiatan OSIS

Jika user meminta memory dihapus karena sudah selesai,
buat SATU baris dengan format:

[DELETE_MEMORY] DD/MM/YYYY|HH:MM|WIB|KEGIATAN

Jika user bertanya tentang jadwal hari ini,
gunakan memory hari ini yang diberikan sistem.

Jangan membuat memory jika user tidak meminta
sesuatu untuk diingat.

Jika membuat atau menghapus memory,
tetap berikan respons bahasa Jepang setelah baris command.

{memory_context}
"""

        # =================================================
        # GENERATE AI RESPONSE
        # =================================================

        print(
            "🤖 CHAT PROVIDER:",
            provider
        )

        print(
            "🎯 MAX OUTPUT TOKENS:",
            max_output_tokens
        )


        if provider == "openai":

            ai_response = (
                generate_openai_response(
                    system_instruction=
                        system_instruction,

                    user_message=
                        user_message,

                    raw_history=
                        raw_history,

                    max_output_tokens=
                        max_output_tokens
                )
            )


        else:

            ai_response = (
                generate_gemini_response(
                    system_instruction=
                        system_instruction,

                    user_message=
                        user_message,

                    raw_history=
                        raw_history,

                    max_output_tokens=
                        max_output_tokens
                )
            )

        if not ai_response:
            ai_response = "わかりません"

        # =================================================
        # PROCESS MEMORY
        # =================================================

        (
            clean_response,
            memory_actions
        ) = process_memory_output(
            ai_response
        )


        if not clean_response:

            clean_response = "わかりました"


        # =================================================
        # AUTO TRANSLATE JP -> ID
        # GPT / Gemini tidak perlu menghasilkan ID.
        # =================================================

        clean_response = build_bilingual_response(
            clean_response
        )


        # =================================================
        # SAVE CHAT
        # =================================================

        memory_manager.save_message(

            session_id,

            "user",

            user_message
        )


        memory_manager.save_message(

            session_id,

            "model",

            clean_response
        )


        # =================================================
        # RESPONSE
        # =================================================

        return jsonify({

            "response":
                clean_response,

            "session_id":
                session_id,

            "status":
                "success",

            "provider":
                provider,

            "max_output_tokens":
                max_output_tokens,

            "memory_actions":
                memory_actions

        })


    except Exception as e:

        print(
            "ERROR DETAIL:",
            e
        )


        return jsonify({

            "error":
                f"Ada masalah: {str(e)}"

        }), 500


# =========================================================
# MEMORY API
# =========================================================

@app.route(
    '/api/memory',
    methods=['GET']
)
def get_memory():


    return jsonify({

        "memories":
            read_memories()

    })


@app.route(
    '/api/memory/today',
    methods=['GET']
)
def get_memory_today():


    return jsonify({

        "date":
            datetime.now().strftime(
                "%d/%m/%Y"
            ),

        "memories":
            get_today_memories()

    })


# =========================================================
# SESSION INFO
# =========================================================

@app.route(
    '/api/sessions/<session_id>',
    methods=['GET']
)
def get_session_info(
    session_id
):


    session = (
        memory_manager
        .get_session(
            session_id
        )
    )


    if not session:

        return jsonify({

            'error':
                'Session tidak ditemukan!'

        }), 404


    raw_history = (
        memory_manager
        .get_conversation_history(
            session_id
        )
    )


    history = convert_history(
        raw_history
    )


    return jsonify({

        'session':
            session,

        'history':
            history

    })


# =========================================================
# DELETE SESSION
# =========================================================

@app.route(
    '/api/sessions/<session_id>',
    methods=['DELETE']
)
def delete_session(
    session_id
):


    memory_manager.delete_session(
        session_id
    )


    return jsonify({

        'message':
            'Session dihapus!'

    })


# =========================================================
# PERSONALITIES
# =========================================================

@app.route(
    '/api/personalities',
    methods=['GET']
)
def get_personalities():


    return jsonify(
        config.PERSONALITY_TEMPLATES
    )


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def not_found(error):


    return app.send_static_file(
        'index.html'
    )

# =========================================================
# JUKEBOX API
# =========================================================

@app.route(
    "/api/songs",
    methods=["GET"]
)
def get_songs():

    try:

        if not os.path.exists(
            SONGS_FOLDER
        ):

            os.makedirs(
                SONGS_FOLDER,
                exist_ok=True
            )


        songs = []


        for filename in os.listdir(
            SONGS_FOLDER
        ):

            file_path = os.path.join(
                SONGS_FOLDER,
                filename
            )


            if not os.path.isfile(
                file_path
            ):
                continue


            if not filename.lower().endswith(
                SUPPORTED_AUDIO
            ):
                continue


            title = os.path.splitext(
                filename
            )[0]


            songs.append({

                "title":
                    title,

                "filename":
                    filename,

                "url":
                    "/songs/" + filename

            })


        songs.sort(
            key=lambda song:
                song["title"].lower()
        )


        return jsonify({

            "status":
                "success",

            "count":
                len(songs),

            "songs":
                songs

        })


    except Exception as e:

        print(
            "JUKEBOX ERROR:",
            e
        )


        return jsonify({

            "status":
                "error",

            "error":
                str(e),

            "songs":
                []

        }), 500

# =========================================================
# START SERVER
# =========================================================

if __name__ == '__main__':


    print(
        "🚀 JayDream AI Started!"
    )


    print(
        "📍 http://localhost:5000"
    )


    print(
        "🎵 Local Songs:",
        SONGS_FOLDER
    )


    print(
        "🎵 Spotify: /api/spotify/login"
    )


    print(
        "🧠 Memory: memory.txt"
    )


    print(
        "🤖 AI Providers: HTML selector (default:",
        DEFAULT_AI_PROVIDER + ")"
    )


    app.run(

        debug=False,

        host='0.0.0.0',

        port=5000
    )