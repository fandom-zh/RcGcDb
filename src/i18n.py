import sys, logging, gettext
from collections import defaultdict

logger = logging.getLogger("rcgcdb.i18n")
supported_languages = ('de', 'hi', 'pl', 'pt-br', 'ru', 'zh-hans', 'zh-hant', 'es')
translated_files = ('wiki', 'misc', 'formatters')

langs = defaultdict(dict)
for lang in supported_languages:
	for file in translated_files:
		try:
			langs[lang][file] = gettext.translation(file, localedir='locale', languages=[lang])
		except FileNotFoundError:
			logger.error(f"Language: {lang}")
			raise
for file in translated_files:
	langs["en"][file] = gettext.NullTranslations()
