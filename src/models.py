from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv, find_dotenv
from os import getenv

from src.config import (MODEL)

load_dotenv(find_dotenv())
DEEPSEEK_API_KEY = getenv("DEEPSEEK_API_KEY")

def get_model():
    return ChatDeepSeek(
        model_name = MODEL,
        api_key = DEEPSEEK_API_KEY
    )