xgettext -L Python --package-name=RcGcDw -o locale/templates/discussion_formatters.pot src/formatters/discussions.py
xgettext -L Python --package-name=RcGcDw -o locale/templates/rc_formatters.pot src/formatters/rc.py
xgettext -L Python --package-name=RcGcDw -o locale/templates/wiki.pot src/wiki.py
xgettext -L Python --package-name=RcGcDw -o locale/templates/discord.pot src/formatters/discord.py
xgettext -L Python --package-name=RcGcDw -o locale/templates/misc.pot src/misc.py

cd ..
declare -a StringArray=("discussion_formatters" "rc_formatters" "discord" "wiki" "misc")
for language in de pl pt-br
do
  for file in ${StringArray[@]}; do
    msgmerge -U locale/$language/LC_MESSAGES/$file.po locale/templates/$file.pot
  done
done
