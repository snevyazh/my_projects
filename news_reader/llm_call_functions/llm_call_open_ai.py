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
    api_key = os.getenv("OPEN_AI_KEY")
    if not api_key:
        raise ValueError("OPEN_AI_KEY not found in environment variables.")

    client = OpenAI(api_key=api_key)
    return client


def print_retry_attempt(retry_state):
    """Prints a custom message to the console before waiting."""
    exception = retry_state.outcome.exception()
    print(f"[WARNING] OpenAI API Issue: {exception}. Pausing {WAIT_SECONDS}s... (Attempt {retry_state.attempt_number})")


@retry(
    wait=wait_fixed(WAIT_SECONDS),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(Exception),
    before_sleep=print_retry_attempt,
)
def call_llm(model_id, prompt):
    """
    Calls the OpenAI API using the modern chat completion syntax.
    """
    client = get_model()

    try:
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "You are a helpful news summarizer. Be factual and concise."},
                {"role": "user", "content": prompt}
            ]
        )

        return response.choices[0].message.content

    except Exception as e:
        # tenacity catches it and retries
        raise e