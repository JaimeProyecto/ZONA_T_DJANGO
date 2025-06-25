# core/decorators.py

from django.contrib.auth.models import Group
from django.shortcuts import redirect
from functools import wraps


def es_admin(user):
    """
    True si autenticado y en el grupo 'admin'.
    """
    return user.is_authenticated and user.groups.filter(name="admin").exists()


def es_vendedor(user):
    """
    True si autenticado y en el grupo 'vendedor'.
    """
    return user.is_authenticated and user.groups.filter(name="vendedor").exists()
