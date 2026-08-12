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