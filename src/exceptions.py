class WikiError(Exception):
	pass

class WikiServerError(Exception):
	def __init__(self, exception: BaseException):
		self.exception = exception


class WikiNotFoundError(Exception):
	pass

class WikiRemovedError(Exception):
	pass

class WikiUnauthorizedError(Exception):
	pass

class OtherWikiError(Exception):
	pass

class QueueEmpty(Exception):
	pass

class ListFull(Exception):
	pass

class EmbedListFull(Exception):
	pass

class TagNotFound(Exception):
	pass

class ServerError(Exception):
	"""Exception for when a request fails because of Server error"""
	pass


class ClientError(Exception):
	"""Exception for when a request failes because of Client error"""

	def __init__(self, request):
		self.message = f"Client have made wrong request! {request.status_code}: {request.reason}. {request.text}"
		super().__init__(self.message)


class BadRequest(Exception):
	"""When type of parameter given to request making method is invalid"""
	def __init__(self, object_type):
		self.message = f"params must be either a strong or OrderedDict object, not {type(object_type)}!"
		super().__init__(self.message)


class MediaWikiError(Exception):
	"""When MediaWiki responds with an error"""
	def __init__(self, errors):
		self.message = f"MediaWiki returned the following errors: {errors}!"
		super().__init__(self.message)

class NoDomain(Exception):
	"""When given domain does not exist"""
	pass

class WikiExists(Exception):
	"""When given wiki already exists"""
	pass


class ExhaustedDiscordBucket(BaseException):
	def __init__(self, remaining: int, is_global: bool):
		self.remaining = remaining
		self.is_global = is_global
