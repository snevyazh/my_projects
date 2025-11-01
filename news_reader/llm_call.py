from tenacity import (
    retry,
    wait_fixed,
    stop_after_attempt,
    retry_if_exception_type,
    before_sleep
)
import google.generativeai as genai
import os

def get_model():
    api_key = "AIzaSyCCCwtrdT3TRhLeiyhxN1TbRfJWxqz-1rY"
    # api_key = os.getenv("KEY")
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel('gemini-2.0-flash')

    return model

def print_retry_attempt(retry_state):
    """Prints a custom message to the console before waiting."""
    print(f"API call failed with: {retry_state.outcome.exception()}. Retrying in 30 seconds... (Attempt {retry_state.attempt_number})")


# @retry(
#     wait=wait_fixed(30),  # Wait 30 seconds between retries
#     stop=stop_after_attempt(5),  # Stop after 5 attempts
#     retry=retry_if_exception_type(Exception),  # Retry on any exception
#     before_sleep=print_retry_attempt,  # Print a message before sleeping
# )
def call_llm(model, prompt):

    try:
        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        print(f"An error occurred while calling the Gemini API: {e}")
        return None

