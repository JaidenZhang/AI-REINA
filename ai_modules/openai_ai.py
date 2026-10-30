import os

from openai import OpenAI

from dotenv import load_dotenv


# =========================================================
# ENV
# =========================================================

load_dotenv()


AI_PROVIDER = "openai"

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY"
)

OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.6-luna"
)


if not OPENAI_API_KEY:

    raise RuntimeError(
        "OPENAI_API_KEY belum ada di .env"
    )


client = OpenAI(
    api_key=OPENAI_API_KEY
)


# =========================================================
# CONVERT HISTORY
# =========================================================

def _convert_history(raw_history):

    messages = []


    for msg in raw_history:

        content = (
            msg.get("content") or ""
        ).strip()


        if not content:

            continue


        # JayDream menggunakan user-history-only.
        # Jawaban AI lama tidak dikirim kembali ke API.

        if msg.get("role") != "user":

            continue


        messages.append({

            "role":
                "user",

            "content":
                content

        })


    return messages


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
    # BUILD INPUT
    # =====================================================

    messages = _convert_history(
        raw_history
    )


    messages.append({

        "role":
            "user",

        "content":
            user_message

    })


    # =====================================================
    # OPENAI RESPONSES API
    # =====================================================

    response = client.responses.create(

        model=
            OPENAI_MODEL,

        instructions=
            system_instruction,

        input=
            messages,

        max_output_tokens=
            max_output_tokens

    )


    # =====================================================
    # RESPONSE
    # =====================================================

    return response.output_text or ""