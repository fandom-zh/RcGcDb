import argparse

parser = argparse.ArgumentParser(description="Starts the bot to retrieve wiki recent changes.")
parser.add_argument("-d", "--debug", action='store_true', help="Starts debugging session, will cause exceptions to return immediately")
command_line_args = parser.parse_args()
