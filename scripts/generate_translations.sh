cd ..
xgettext -L Python --package-name=RcGcDb -o locale/templates/discussion_formatters.pot src/formatters/discussions.py
xgettext -L Python --package-name=RcGcDb -o locale/templates/rc_formatters.pot src/formatters/rc.py
xgettext -L Python --package-name=RcGcDb -o locale/templates/wiki.pot src/wiki.py
xgettext -L Python --package-name=RcGcDb -o locale/templates/discord.pot src/discord.py
xgettext -L Python --package-name=RcGcDb -o locale/templates/misc.pot src/misc.py

declare -a StringArray=("discussion_formatters" "rc_formatters" "discord" "wiki" "misc")
for language in de pl pt-br
do
  for file in ${StringArray[@]}; do
    msgmerge -U locale/$language/LC_MESSAGES/$file.po locale/templates/$file.pot
  done
  msgmerge -o locale/$language/LC_MESSAGES/discussion_formatters.po ~/PycharmProjects/RcGcDw/locale/$language/LC_MESSAGES/discussion_formatters.po locale/$language/LC_MESSAGES/discussion_formatters.po
  msgmerge -o locale/$language/LC_MESSAGES/rc_formatters.po ~/PycharmProjects/RcGcDw/locale/$language/LC_MESSAGES/rc_formatters.po locale/$language/LC_MESSAGES/rc_formatters.po
  msgmerge -o locale/$language/LC_MESSAGES/wiki.po ~/PycharmProjects/RcGcDw/locale/$language/LC_MESSAGES/rc.po locale/$language/LC_MESSAGES/wiki.po
  msgmerge -o locale/$language/LC_MESSAGES/misc.po ~/PycharmProjects/RcGcDw/locale/$language/LC_MESSAGES/misc.po locale/$language/LC_MESSAGES/misc.po
done
for language in en fr de pl pt_BR ru es tr nl zh_Hans zh_Hant
do
  wget https://weblate.frisk.space/widgets/wiki-bot/$language/discord/svg-badge.svg
  convert -size 111x20 svg-badge.svg translation-pngs/wiki-bot-${language//_/-}.png
  rm svg-badge.svg
done
