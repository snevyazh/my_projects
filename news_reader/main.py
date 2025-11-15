import argparse
from main_process import process_all

def main(parameters=None):
    process_all.run_process(parameters)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--scrap',
                        help='if we need to run scrapper or use the file',
                        required=True,
                        default='yes')
    parser.add_argument('-d', '--date',
                        help='scrap file date',
                        required=False,
                        default='yes')
    args = parser.parse_args()
    if args.scrap not in ['yes', 'no']:
        raise Exception("Illegal input")
    # TODO add check the date format

    main(args)