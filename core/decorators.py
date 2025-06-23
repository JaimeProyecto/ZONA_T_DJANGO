# core/decorators.py


def es_vendedor(user):
    """
    Devuelve True si el usuario está autenticado y tiene el rol 'vendedor'.
    Ajusta 'vendedor' al nombre exacto que uses en tu tabla de roles.
    """
    return user.is_authenticated and user.roles.filter(name="vendedor").exists()


def es_admin(user):
    """
    Devuelve True si el usuario está autenticado y tiene el rol 'admin'.
    Ajusta 'admin' al nombre exacto que uses en tu tabla de roles.
    """
    return user.is_authenticated and user.roles.filter(name="admin").exists()
