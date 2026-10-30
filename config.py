import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    MEMORY_DB_PATH = os.getenv('MEMORY_DB_PATH', './chat_memory.db')
    
    PERSONALITY_TEMPLATES = {
        "default":"Kamu agak tsundere, kadang tidak penurut, tapi tetap pintar. ",
    }
    