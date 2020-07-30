import sys, logging, gettext

logger = logging.getLogger("rcgcdb.i18n")

try:
	en = gettext.translation('rcgcdw', localedir='locale', languages=["en"])
	de = gettext.translation('rcgcdw', localedir='locale', languages=["de"])
	pl = gettext.translation('rcgcdw', localedir='locale', languages=["pl"])
	pt = gettext.translation('rcgcdw', localedir='locale', languages=["pt-br"])
	#ru = gettext.translation('rcgcdw', localedir='locale', languages=["ru"])
	#uk = gettext.translation('rcgcdw', localedir='locale', languages=["uk"])
	#fr = gettext.translation('rcgcdw', localedir='locale', languages=["fr"])
	langs = {"en": en, "de": de, "pl": pl, "pt": pt}
	#langs = {"en": en, "de": de, "pl": pl, "pt": pt, "ru": ru, "uk": uk, "fr": fr}
except FileNotFoundError:
	logger.critical("No language files have been found. Make sure locale folder is located in the directory.")
	sys.exit(1)

#ngettext = en.ngettext