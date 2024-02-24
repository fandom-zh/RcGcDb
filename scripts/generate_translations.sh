cd ..
# Formatters
#find extensions/ -name '*.py' -print | xargs xgettext -L Python --package-name=RcGcDb --keyword=pgettext:1c,2 --keyword=npgettext:1c,2,3 -o "locale/templates/formatters.pot" src/api/util.py
for language in de pl pt-br hi ru uk zh-hans zh-hant fr es it
  do
    msgmerge -U locale/$language/LC_MESSAGES/formatters.po ~/Projects/RcGcDw/locale/$language/LC_MESSAGES/formatters.po
#    msgmerge -U locale/$language/LC_MESSAGES/formatters.po locale/templates/formatters.pot
done


xgettext -L Python --package-name=RcGcDb -o locale/templates/wiki.pot src/wiki.py
xgettext -L Python --package-name=RcGcDb -o locale/templates/misc.pot src/misc.py

declare -a StringArray=("wiki" "misc")
for language in de pl pt-br hi ru uk zh-hans zh-hant fr es it
do
  for file in ${StringArray[@]}; do
    msgmerge -U locale/$language/LC_MESSAGES/$file.po locale/templates/$file.pot
  done
  msgmerge -o locale/$language/LC_MESSAGES/wiki.po ~/Projects/RcGcDw/locale/$language/LC_MESSAGES/rc.po locale/$language/LC_MESSAGES/wiki.po
  msgmerge -o locale/$language/LC_MESSAGES/wiki.po ~/Projects/RcGcDw/locale/$language/LC_MESSAGES/rcgcdw.po locale/$language/LC_MESSAGES/wiki.po
  msgmerge -o locale/$language/LC_MESSAGES/misc.po ~/Projects/RcGcDw/locale/$language/LC_MESSAGES/misc.po locale/$language/LC_MESSAGES/misc.po
  for file in wiki misc formatters
  do
    msgfmt -o locale/$language/LC_MESSAGES/$file.mo locale/$language/LC_MESSAGES/$file.po
  done
done
# for language in locale/*/LC_MESSAGES
for language in de pl pt-br hi ru uk zh-hans zh-hant fr es it
do
  wget https://translate.wikibot.de/widgets/rcgcdw/$(basename ${language//\/LC_MESSAGES/})/-/svg-badge.svg
  convert -background none svg-badge.svg locale/widgets/$(basename ${language//\/LC_MESSAGES/}).png
  rm svg-badge.svg
done
