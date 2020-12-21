cd ..
xgettext -L Python --package-name=RcGcDb -o locale/templates/discussion_formatters.pot src/formatters/discussions.py
xgettext -L Python --package-name=RcGcDb -o locale/templates/rc_formatters.pot src/formatters/rc.py
xgettext -L Python --package-name=RcGcDb -o locale/templates/wiki.pot src/wiki.py
xgettext -L Python --package-name=RcGcDb -o locale/templates/discord.pot src/discord.py
xgettext -L Python --package-name=RcGcDb -o locale/templates/misc.pot src/misc.py

declare -a StringArray=("discussion_formatters" "rc_formatters" "discord" "wiki" "misc")
for language in de pl pt-br hi ru uk zh-hans zh-hant
do
  for file in ${StringArray[@]}; do
    msgmerge -U locale/$language/LC_MESSAGES/$file.po locale/templates/$file.pot
  done
  msgmerge -o locale/$language/LC_MESSAGES/discussion_formatters.po ~/PycharmProjects/RcGcDw/locale/$language/LC_MESSAGES/discussion_formatters.po locale/$language/LC_MESSAGES/discussion_formatters.po
  msgmerge -o locale/$language/LC_MESSAGES/rc_formatters.po ~/PycharmProjects/RcGcDw/locale/$language/LC_MESSAGES/rc_formatters.po locale/$language/LC_MESSAGES/rc_formatters.po
  msgmerge -o locale/$language/LC_MESSAGES/wiki.po ~/PycharmProjects/RcGcDw/locale/$language/LC_MESSAGES/rc.po locale/$language/LC_MESSAGES/wiki.po
  msgmerge -o locale/$language/LC_MESSAGES/misc.po ~/PycharmProjects/RcGcDw/locale/$language/LC_MESSAGES/misc.po locale/$language/LC_MESSAGES/misc.po
  for file in ${StringArray[@]}; do
    msgfmt -o locale/$language/LC_MESSAGES/$file.mo locale/$language/LC_MESSAGES/$file.po
  done
done
for language in locale/*/LC_MESSAGES
do
  wget https://weblate.frisk.space/widgets/rcgcdw/$(basename ${language//\/LC_MESSAGES/})/-/svg-badge.svg
  convert -background none svg-badge.svg locale/widgets/$(basename ${language//\/LC_MESSAGES/}).png
  rm svg-badge.svg
done
