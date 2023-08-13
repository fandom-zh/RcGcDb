import json, sys, logging

try:  # load settings
	with open("settings.json", encoding="utf8") as sfile:
		settings = json.load(sfile)
		if "user-agent" in settings["header"]:
			settings["header"]["user-agent"] = settings["header"]["user-agent"].format(version="1.9 Beta")  # set the version in the useragent
except FileNotFoundError:
	logging.critical("No config file could be found. Please make sure settings.json is in the directory.")
	sys.exit(1)