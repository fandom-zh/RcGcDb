#  This file is part of Recent changes Goat compatible Discord bot (RcGcDb).
#
#  RcGcDb is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  RcGcDw is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with RcGcDb.  If not, see <http://www.gnu.org/licenses/>.

# Made just to avoid circular imports
from typing import Callable
formatter_hooks: dict[str, dict[str, Callable]] = {"embed": {}, "compact": {}}
pre_hooks = []
post_hooks = []