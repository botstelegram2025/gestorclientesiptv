# utils/validacoes.py

import re

def telefone_valido(telefone: str) -> bool:
    """
    Verifica se o telefone contém apenas dígitos e tem entre 10 e 11 caracteres (com DDD).
    Ex: 11999998888
    """
    return bool(re.match(r'^\\d{10,11}$', telefone))
