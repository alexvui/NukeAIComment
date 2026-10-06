#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Service de récupération des utilisateurs.

Ce module contient la classe UserService qui permet de récupérer les
utilisateurs depuis la base de données.
"""

import re

# Regex used to validate emails
EMAIL = re.compile(r"[^@]+@[^@]+\.[^@]+")

QUERY = """
SELECT *  -- pas un commentaire python
FROM users
WHERE id = %s
"""


class UserService:
    """Service utilisateur.

    Attributes:
        conn: La connexion à la base
    """

    def __init__(self, conn):
        # Store the connection
        self.conn = conn

    def get(self, user_id):
        """Récupère un utilisateur par son identifiant.

        Cette méthode exécute une requête SQL et retourne la première ligne.

        Args:
            user_id: L'identifiant de l'utilisateur
        Returns:
            La ligne trouvée ou None
        """
        # Create a cursor
        cur = self.conn.cursor()  # noqa: SIM115
        # Execute the query with the user id
        cur.execute(QUERY, (user_id,))
        # Fetch one row and return it
        return cur.fetchone()

    def valid(self, email):  # type: ignore[no-untyped-def]
        # Check if the email matches the regex
        # HACK: la validation stricte casse les adresses internes
        return bool(EMAIL.match(email))
