from llm_call_functions import llm_call_open_ai as llm_call

#

import os
# import google.generativeai as genai
# from dotenv import load_dotenv

# Load your .streamlit/secrets.toml manually or set env var
# os.environ["GEMINI_API_KEY"] = "YOUR_KEY_HERE"

# api_key = "AIzaSyCCCwtrdT3TRhLeiyhxN1TbRfJWxqz-1rY"
# genai.configure(api_key=api_key)
#
# print("Listing available models...")
# for m in genai.list_models():
#     if 'generateContent' in m.supported_generation_methods:
#         print(f"Name: {m.name}")
# url = "https://www.ynet.co.il/news/article/r1e4wf7yzx"
# print('---'*70, scrapper.get_full_article_text(url, print_every_step=True))
#
#
# feeds = ["https://www.israelhayom.co.il/rss.xml"]
# full_text_for_llm, articles_num = israel_rss_reader.get_text_for_llm(feeds, time_window=1)
#



# print(f"Collected {articles_num} articles for the LLM digest.")
# print(f"Text tokens number is {count_tokens(full_text_for_llm)}")

# prompt = "what is the capital of france"
# model = llm_call.get_model()
# result = llm_call.call_llm(model, prompt)
# print(result)

# url = "https://www.linkedin.com/company/twitch-tv"
# result = scrapper.get_full_article_text(url)
# print(result)


from openai import OpenAI


OPEN_AI_KEY = "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"

model = OpenAI(api_key=OPEN_AI_KEY)

def call_llm(model, prompt):

    model_id = "gpt-4o-mini"

    response = model.responses.create(
            model=model_id,
            input=prompt,
            temperature=0.01
        )
    return response.output[0].content[0].text

prompt = "What is the capital of France?"
print(call_llm(model, prompt))






