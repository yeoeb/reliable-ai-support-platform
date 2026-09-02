class UserAlreadyExistsError(Exception):
    pass


class PersistenceUnavailableError(Exception):
    pass

class InvalidCredentialsError(Exception):
    pass

class DefaultRoleNotConfiguredError(Exception):
    pass

class UserNotFoundError(Exception):
    pass


class RoleNotFoundError(Exception):
    pass


class InvalidKnowledgeContentError(Exception):
    pass



class KnowledgeDocumentNotFoundError(Exception):
    pass


class EmbeddingStateConflictError(Exception):
    pass


class EmbeddingProviderError(Exception):
    pass


class EmbeddingProviderNotConfiguredError(EmbeddingProviderError):
    pass


class EmbeddingProviderUnavailableError(EmbeddingProviderError):
    pass


class InvalidEmbeddingProviderResponseError(EmbeddingProviderError):
    pass
