import sys, logging, gettext
from collections import defaultdict

logger = logging.getLogger("rcgcdb.i18n")
supported_languages = ('de', 'hi', 'pl', 'pt-br', 'ru', 'zh-hans', 'zh-hant')
translated_files = ('wiki', 'misc', 'discord', 'rc_formatters', 'discussion_formatters')

try:
	langs = defaultdict(dict)
	for lang in supported_languages:
		for file in translated_files:
			langs[lang][file] = gettext.translation(file, localedir='locale', languages=[lang])
	for file in translated_files:
		langs["en"][file] = gettext.NullTranslations()
except FileNotFoundError:
	logger.critical("No language files have been found. Make sure locale folder is located in the directory.")
	sys.exit(1)
