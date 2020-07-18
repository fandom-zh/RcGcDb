import sys, logging, gettext

logger = logging.getLogger("rcgcdb.i18n")

try:
	en = gettext.translation('rcgcdb', localedir='locale', languages=["en"])
	de = gettext.translation('rcgcdb', localedir='locale', languages=["de"])
	pl = gettext.translation('rcgcdb', localedir='locale', languages=["pl"])
	pt = gettext.translation('rcgcdb', localedir='locale', languages=["pt"])
	ru = gettext.translation('rcgcdb', localedir='locale', languages=["ru"])
	uk = gettext.translation('rcgcdb', localedir='locale', languages=["uk"])
	fr = gettext.translation('rcgcdb', localedir='locale', languages=["fr"])
	langs = {"en": en, "de": de, "pl": pl, "pt": pt, "ru": ru, "uk": uk, "fr": fr}
except FileNotFoundError:
	logger.critical("No language files have been found. Make sure locale folder is located in the directory.")
	sys.exit(1)

#ngettext = en.ngettext