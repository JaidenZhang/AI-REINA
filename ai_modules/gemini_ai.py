import os

import google.generativeai as genai

from dotenv import load_dotenv


# =========================================================
# ENV
# =========================================================

load_dotenv()


AI_PROVIDER = "gemini"

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "models/gemini-2.5-flash"
)


if not GEMINI_API_KEY:

    raise RuntimeError(
        "GEMINI_API_KEY belum ada di .env"
    )


genai.configure(
    api_key=GEMINI_API_KEY
)


# =========================================================
# CONVERT HISTORY
# =========================================================

def _convert_history(raw_history):

    history = []


    for msg in raw_history:

        content = (
            msg.get("content") or ""
        ).strip()


        if not content:

            continue


        # app.py sekarang mengirim user-history-only.
        # Guard ini memastikan jawaban AI lama tidak ikut
        # dikirim kembali ke Gemini.

        if msg.get("role") != "user":

            continue


        history.append({

            "role":
                "user",

            "parts": [

                {
                    "text":
                        content
                }

            ]

        })


    return history


# =========================================================
# GENERATE RESPONSE
# =========================================================

def generate_response(
    system_instruction,
    user_message,
    raw_history,
    max_output_tokens=300
):

    # =====================================================
    # VALIDATE TOKEN LIMIT
    # =====================================================

    try:

        max_output_tokens = int(
            max_output_tokens
        )

    except (
        TypeError,
        ValueError
    ):

        max_output_tokens = 300


    max_output_tokens = max(
        50,
        min(
            max_output_tokens,
            2000
        )
    )


    # =====================================================
    # MODEL
    # =====================================================

    model = genai.GenerativeModel(

        model_name=
            GEMINI_MODEL,

        system_instruction=
            system_instruction,

        generation_config=
            genai.GenerationConfig(

                max_output_tokens=
                    max_output_tokens

            )

    )


    # =====================================================
    # CHAT
    # =====================================================

    chat_session = model.start_chat(

        history=
            _convert_history(
                raw_history
            )

    )


    response = chat_session.send_message(
        user_message
    )


    # =====================================================
    # RESPONSE
    # =====================================================

    if not response:

        return ""


    try:

        return response.text or ""

    except Exception:

        return ""