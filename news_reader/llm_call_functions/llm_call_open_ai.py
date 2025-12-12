import warnings
import os
from openai import OpenAI
from tenacity import (
    retry,
    wait_fixed,
    stop_after_attempt,
    retry_if_exception_type,
    before_sleep
)

# Suppress warnings
warnings.filterwarnings('ignore')

# Wait 20 seconds between retries
WAIT_SECONDS = 20


def get_model():
    """
    Initializes the OpenAI client.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables.")

    client = OpenAI(api_key=api_key)
    return client


def print_retry_attempt(retry_state):
    """Prints a custom message to the console before waiting."""
    exception = retry_state.outcome.exception()
    print(f"[WARNING] OpenAI API Issue: {exception}. Pausing {WAIT_SECONDS}s... (Attempt {retry_state.attempt_number})")


# @retry(
#     wait=wait_fixed(WAIT_SECONDS),
#     stop=stop_after_attempt(3),
#     retry=retry_if_exception_type(Exception),
#     before_sleep=print_retry_attempt,
# )
def call_llm(client, prompt):
    """
    Calls the OpenAI API using the modern 'client.responses.create' syntax.
    """
    # We use gpt-4o-mini for cost efficiency ($0.15/1M tokens)
    # You can change this to "gpt-4o" or "gpt-5.2" if you want higher intelligence.
    model_id = "gpt-4o-mini"

    try:
        # Updated syntax per your request and latest OpenAI docs
        response = client.responses.create(
            model=model_id,
            instructions="You are a helpful news summarizer. Be factual and concise.",
            input=prompt
        )

        # Access the text directly
        return response.output_text

    except Exception as e:
        # Raise the error so Tenacity catches it and retries
        raise e