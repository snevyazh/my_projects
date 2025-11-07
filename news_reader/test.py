import israel_rss_reader
import scrapper_v2 as scrapper
from custom_functions import count_tokens
import llm_call_open_ai as llm_call
#


# url = "https://www.ynet.co.il/news/article/r1e4wf7yzx"
# print('---'*70, scrapper.get_full_article_text(url, print_every_step=True))
#
#
# feeds = ["https://www.israelhayom.co.il/rss.xml"]
# full_text_for_llm, articles_num = israel_rss_reader.get_text_for_llm(feeds, time_window=1)
#



# print(f"Collected {articles_num} articles for the LLM digest.")
# print(f"Text tokens number is {count_tokens(full_text_for_llm)}")

prompt = "what is the capital of france"
model = llm_call.get_model()
result = llm_call.call_llm(model, prompt)
print(result)

# url = "https://www.linkedin.com/company/twitch-tv"
# result = scrapper.get_full_article_text(url)
# print(result)





