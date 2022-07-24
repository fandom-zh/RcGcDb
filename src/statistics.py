import time

import aiohttp.web_request

from src.config import settings
from typing import Union, Optional
from enum import Enum


class LogType(Enum):
    CONNECTION_ERROR: 1
    HTTP_ERROR: 2
    MEDIAWIKI_ERROR: 3
    VALUE_UPDATE: 4

queue_limit = settings.get("queue_limit", 30)


class Log:
    """Log class represents an event that happened to a wiki fetch. Main purpose of those logs is debug and error-tracking."""
    def __init__(self, **kwargs):
        self.type: LogType = kwargs["type"]
        self.time: int = int(time.time())
        self.title: str = kwargs["title"]
        self.details: Optional[str] = kwargs.get("details", None)

class LimitedList(list):
    def __init__(self, *args):
        list.__init__(self, *args)

    def append(self, obj: Log) -> None:
        if len(self) > queue_limit:
            self.pop()


class Statistics:
    def __init__(self, rc_id: Optional[int], discussion_id: Optional[int]):
        self.last_request: Optional[aiohttp.web_request.Request] = None
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