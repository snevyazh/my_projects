import warnings
# suppress warnings
warnings.filterwarnings('ignore')
from tenacity import (
    retry,
    wait_fixed,
    stop_after_attempt,
    retry_if_exception_type,
    before_sleep
)
import google.generativeai as genai
from google.generativeai import types
import os


def get_model():

    api_key = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=api_key)

    # model = genai.GenerativeModel('gemini-2.0-flash')
    model = genai.GenerativeModel('gemini-2.5-pro')

    return model

def print_retry_attempt(retry_state):
    """Prints a custom message to the console before waiting."""
    print(f"API call failed with: {retry_state.outcome.exception()}. Retrying in 30 seconds... (Attempt {retry_state.attempt_number})")


@retry(
    wait=wait_fixed(61),  # Wait 30 seconds between retries
    stop=stop_after_attempt(5),  # Stop after 5 attempts
    retry=retry_if_exception_type(Exception),  # Retry on any exception
    before_sleep=print_retry_attempt,  # Print a message before sleeping
)
def call_llm(model, prompt):

    generation_config = types.GenerationConfig(
        temperature=0.1
    )
    response = model.generate_content(prompt,
                                      generation_config=generation_config
                                      )
    return response.text



