import sys, logging, gettext

logger = logging.getLogger("rcgcdb.i18n")

try:
	lang = gettext.translation('rcgcdb', localedir='locale', languages=["en"])
except FileNotFoundError:
	logger.critical("No language files have been found. Make sure locale folder is located in the directory.")
	sys.exit(1)

lang.install()
ngettext = lang.ngettext