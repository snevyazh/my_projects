

def get_the_html(run_time, html_body_content):
    css_style = """
            body {
                direction: rtl;
                font-family: Arial, sans-serif;
                font-size: 20px; /* Increased font size for readability */
                line-height: 1.8;
                padding: 25px;
                background-color: #f8f9fa;
                color: #343a40;
            }
            h1, h2, h3, h4, h5, h6 {
                color: #007bff;
                border-bottom: 2px solid #dee2e6;
                padding-bottom: 5px;
                margin-top: 30px;
            }
            ul {
                list-style-type: none; /* Remove default bullets */
                padding-right: 0;
                margin-right: 20px;
            }
            li {
                margin-bottom: 20px; /* Increase space between bullets */
                border-right: 4px solid #007bff; /* Custom bullet/marker on the right */
                padding-right: 15px;
            }
            strong {
                color: #dc3545; /* Highlight strong text */
            }
            """

    # 3. Assemble the full HTML document
    html_output = f"""
        <!DOCTYPE html>
        <html lang="he" dir="rtl">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>סיכום חדשות - {run_time}</title>
            <style>
                {css_style}
            </style>
        </head>
        <body>
            {html_body_content}
        </body>
        </html>
        """

    return html_output