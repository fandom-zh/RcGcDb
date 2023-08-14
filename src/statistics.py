import time
from datetime import datetime
import aiohttp.web_request

from src.config import settings
from typing import Union, Optional
from enum import Enum


class LogType(Enum):
    CONNECTION_ERROR = 1
    HTTP_ERROR = 2
    MEDIAWIKI_ERROR = 3
    VALUE_UPDATE = 4
    SCAN_REASON = 5


queue_limit = settings.get("queue_limit", 30)


class Log:
    """Log class represents an event that happened to a wiki fetch. Main purpose of those logs is debug and error-tracking."""
    def __init__(self, **kwargs):
        self.type: LogType = kwargs["type"]
        self.time: int = int(time.time())
        self.title: str = kwargs["title"]
        self.details: Optional[str] = kwargs.get("details", None)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"<Log {self.type.name} at {datetime.fromtimestamp(float(self.time)).isoformat()} on {self.title} with details: {self.details}>"


class LimitedList(list):
    def __init__(self, *args):
        list.__init__(self, *args)

    def append(self, obj: Log) -> None:
        if len(self) > queue_limit:
            self.pop(0)
        super(LimitedList, self).append(obj)

    def __repr__(self):
        return "\n".join(self)


class Statistics:
    def __init__(self, rc_id: Optional[int], discussion_id: Optional[str]):
        self.last_request: Optional[aiohttp.web_request.Request] = None
        self.last_checked_rc: Optional[int] = None
        self.last_action: Optional[int] = rc_id
        self.last_checked_discussion: Optional[int] = None
        self.last_post: Optional[str] = discussion_id
        self.logs: LimitedList[Log] = LimitedList()

    def __str__(self):
        return (f"<last_request={self.last_request}, last_checked_rc={self.last_checked_rc}, last_action={self.last_action},"
                f" last_checked_discussion={self.last_checked_discussion}, last_post={self.last_post}, logs={self.logs}>")

    def update(self, *args: Log, **kwargs: Union[float, int, str]):
        for key, value in kwargs.items():
            self.__setattr__(key, value)
        for log in args:
            self.logs.append(log)

    def filter_by_time(self, time_ago: int, logs: list = None):  # cannot have self.logs in here as this is evaluated once
        """Returns logs with time between time_ago seconds ago and now"""
        time_limit = int(time.time()) - time_ago
        return [x for x in (self.logs if logs is None else logs) if x.time > time_limit]

    def filter_by_type(self, log_type: LogType, logs: list = None):
        """Returns logs with same type as in log_type"""
        return [x for x in (self.logs if logs is None else logs) if x.type == log_type]

    def recent_connection_errors(self) -> int:
        """Count how many connection errors there were recently (2 minutes)"""
        return len(self.filter_by_type(LogType.CONNECTION_ERROR, logs=self.filter_by_time(120)))   # find connection errors from 2 minutes ago
