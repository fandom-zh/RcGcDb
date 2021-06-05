from src.config import settings
from typing import Union, Optional

queue_limit = settings.get("queue_limit", 30)

class Log:
    def __init__(self, **kwargs):



class LimitedList(list):
    def __init__(self, *args):
        list.__init__(self, *args)

    def append(self, obj: Log) -> None:
        if len(self) > queue_limit:
            self.pop()


class Statistics:
    def __init__(self, rc_id: int, discussion_id: int):
        self.last_checked_rc: Optional[int] = None
        self.last_action: Optional[int] = rc_id
        self.last_checked_discussion: Optional[int] = None
        self.last_post: Optional[int] = discussion_id
        self.logs: LimitedList = LimitedList()

    def update(self, *args: Log, **kwargs: dict[str, Union[float, int]]):
        for key, value in kwargs:
            self.__setattr__(key, value)
        for log in args:
            self.logs.append(log)