[![Daily News Bot](https://github.com/snevyazh/my_projects/actions/workflows/daily_news.yml/badge.svg?branch=main)](https://github.com/snevyazh/my_projects/actions/workflows/daily_news.yml)

# News Reader

This project is a Streamlit application that fetches news from a predefined list of RSS feeds, generates a concise news digest using a generative AI model (either Google Gemini or OpenAI's GPT), and presents it in a clean and easy-to-read format.

## Description

The application provides a simple interface to trigger a news digest generation process. It runs a Python script (`main.py`) as a subprocess to fetch and process the news. The script retrieves articles from the RSS feeds specified in the configuration, uses a generative AI model to summarize them, and saves the output to a text file. The Streamlit app then displays the generated summary.

## Features

-   Fetches news from multiple RSS feeds in parallel using a multi-threaded approach.
-   Uses generative AI models (Gemini and OpenAI) to create a news digest.
-   Displays the digest in a Streamlit web application.
-   Real-time logging of the news processing script.
-   Configuration of RSS feeds and models through a TOML file.
-   Secure management of API keys using Streamlit secrets.

## Project Structure

```
news_reader/
├── config/                  # Configuration files
│   └── config.toml
├── main_process/            # Main news processing logic
│   └── main.py
├── output/                  # Generated news digests
├── prompts/                 # Prompts for the LLM
├── rss_reader/              # RSS feed reader
│   └── israel_rss_reader.py
├── web_app/                 # Streamlit web application
│   └── app.py
├── web_scrapper/            # Web scraping functions
├── .streamlit/
│   └── secrets.toml         # API keys and secrets
├── .gitignore
├── README.md
└── requirements.txt
```

## Installation

1.  Clone the repository:
    ```bash
    git clone <repository-url>
    ```
2.  Navigate to the project directory:
    ```bash
    cd news_reader
    ```
3.  Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  **RSS Feeds and Models**: The RSS feeds and the OpenAI model are configured in the `config/config.toml` file.

2.  **API Keys**: The application requires API keys for both Google Gemini and OpenAI. You need to create a `.streamlit/secrets.toml` file in the project's root directory with the following content:
    ```toml
    [secrets]
    GEMINI_API_KEY = "your_gemini_key_here"
    OPEN_AI_KEY = "your_openai_key_here"

    [model]
    open_ai_model = "gpt-4-turbo-preview"
    ```
    Replace the placeholder keys with your actual API keys.

## Usage

To run the application, navigate to the project's root directory and execute the following command in your terminal:

```bash
python -m streamlit run web_app/app.py
```

This will start the Streamlit server and open the application in your web browser. Click the "Run Daily Digest" button to generate a new news summary.

## Dependencies

The project uses the following major dependencies:

-   `streamlit`: For the web application interface.
-   `google-generativeai`: To interact with the Google Gemini model.
-   `openai`: To interact with the OpenAI models.
-   `feedparser`: To parse RSS feeds.
-   `newspaper3k`: To extract article content.
-   `toml`: For configuration file management.

For a complete list of dependencies, please see the `requirements.txt` file.
