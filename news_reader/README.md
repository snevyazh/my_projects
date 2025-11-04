# News Reader

This project is a Streamlit application that fetches news from a predefined list of RSS feeds, generates a concise news digest using a generative AI model, and presents it in a clean and easy-to-read format.

## Description

The application provides a simple interface to trigger a news digest generation process. It runs a Python script (`main.py`) as a subprocess to fetch and process the news. The script retrieves articles from the RSS feeds specified in the configuration, uses a generative AI model to summarize them, and saves the output to a text file. The Streamlit app then displays the generated summary.

## Features

-   Fetches news from multiple RSS feeds.
-   Uses a generative AI model to create a news digest.
-   Displays the digest in a Streamlit web application.
-   Real-time logging of the news processing script.
-   Configuration of RSS feeds through a TOML file.
-   Secure management of API keys using Streamlit secrets.

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

1.  **RSS Feeds**: The RSS feeds are configured in the `config/config.toml` file. You can add or remove feeds from the `ISRAELI_NEWS_FEEDS` list.

2.  **API Key**: The application requires a Gemini API key. You need to create a `.streamlit/secrets.toml` file in the project's root directory with the following content:
    ```toml
    [secrets]
    GEMINI_API_KEY = "your_key_here"
    ```
    Replace `"your_key_here"` with your actual Gemini API key.

## Usage

To run the application, execute the following command in your terminal:

```bash
python -m streamlit run app.py
```

This will start the Streamlit server and open the application in your web browser. Click the "Run Daily Digest" button to generate a new news summary.

## Dependencies

The project uses the following major dependencies:

-   `streamlit`: For the web application interface.
-   `google-generativeai`: To interact with the generative AI model.
-   `feedparser`: To parse RSS feeds.
-   `newspaper3k`: To extract article content.
-   `toml`: For configuration file management.

For a complete list of dependencies, please see the `requirements.txt` file.
