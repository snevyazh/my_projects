import argparse
import time


def main(parameters=None):
    start_time = time.time()
    
    if getattr(parameters, 'telegram', 'no') == 'yes':
        from main_process import telegram_incremental
        telegram_incremental.run_telegram_update()
    else:
        from main_process import process_all
        process_all.run_process(parameters)
        
    print(f"\n\nRun time: {time.time() - start_time:.2f} seconds")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    # -s yes: Scrape new links and save summaries to DB
    parser.add_argument('-s', '--scrap',
                        help='Run scraper?',
                        required=False,
                        default='yes')

    # -r yes: Generate final email from DB
    parser.add_argument('-r', '--report',
                        help='Send final report email?',
                        required=False,
                        default='no')

    # -t yes: Run Incremental Telegram Fetch and Send
    parser.add_argument('-t', '--telegram',
                        help='Run Incremental Telegram fetch?',
                        required=False,
                        default='no')

    parser.add_argument('-d', '--date', help='Date (unused)', required=False)

    args = parser.parse_args()
    main(args)