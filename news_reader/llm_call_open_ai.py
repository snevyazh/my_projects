import warnings
# suppress warnings
warnings.filterwarnings('ignore')
from tenacity import (
    retry,
    wait_fixed,
    stop_after_attempt,
    retry_if_exception_type,
)
import os
from openai import OpenAI
import toml as tomlib


def get_model():
    with open("./.streamlit/secrets.toml", "r") as f:
        config_data = tomlib.load(f)
    api_key = config_data["secrets"]["OPEN_AI_KEY"]
    print(api_key)
    model = OpenAI(api_key=api_key)

    return model


@retry(
    wait=wait_fixed(30),  # Wait 30 seconds between retries
    stop=stop_after_attempt(5),  # Stop after 5 attempts
    retry=retry_if_exception_type(Exception),  # Retry on any exception
)
def call_llm(model, prompt):

    model_id = os.getenv("OPENAI_MODEL")

    try:
        response = model.responses.create(
            model=model_id,
            input=prompt,
            temperature=0.01
        )
        return response.output[0].content[0].text

    except Exception as e:
        print(f"An error occurred while calling the LLM API: {e}")
        return None

