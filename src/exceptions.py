class WikiError(Exception):
	pass

class WikiServerError(Exception):
	pass

class WikiNotFoundError(Exception):
	pass

class WikiRemovedError(Exception):
	pass

class WikiUnauthorizedError(Exception):
	pass

class OtherWikiError(Exception):
	pass