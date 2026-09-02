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


class GenerationProviderError(Exception):
    pass


class GenerationProviderNotConfiguredError(GenerationProviderError):
    pass


class GenerationProviderUnavailableError(GenerationProviderError):
    pass


class InvalidGenerationProviderResponseError(GenerationProviderError):
    pass


class ToolCallingProviderError(Exception):
    pass


class ToolCallingProviderNotConfiguredError(ToolCallingProviderError):
    pass


class ToolCallingProviderUnavailableError(ToolCallingProviderError):
    pass


class InvalidToolCallingProviderResponseError(ToolCallingProviderError):
    pass


class NoAuthorizedToolError(Exception):
    pass


class UnknownToolError(Exception):
    pass


class InvalidToolArgumentsError(Exception):
    pass


class ToolPermissionDeniedError(Exception):
    pass


class ToolExecutionError(Exception):
    pass



class ApprovalNotFoundError(Exception):
    pass


class ApprovalStateConflictError(Exception):
    pass


class ApprovalPermissionDeniedError(Exception):
    pass
