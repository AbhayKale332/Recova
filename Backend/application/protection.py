"""Encryption support for sensitive customer data stored in the database."""

import logging

from cryptography .fernet import Fernet
from sqlalchemy import String ,TypeDecorator

from application .settings import settings

logger =logging .getLogger (__name__ )


def _load_cipher ()->Fernet :
    key =settings .encryption_key
    if not key :


        key =Fernet .generate_key ().decode ()
        logger .warning (
        "ENCRYPTION_KEY is not configured; generated an ephemeral key. Encrypted "
        "fields will not be recoverable after restart. Configure ENCRYPTION_KEY "
        "in the environment for persistent data."
        )
    return Fernet (key .encode ()if isinstance (key ,str )else key )


_cipher =_load_cipher ()


class EncryptedString (TypeDecorator ):
    """Stores a string encrypted at rest, exposes plaintext to the app."""

    impl =String
    cache_ok =True

    def process_bind_param (self ,value ,dialect ):
        if value is None :
            return None
        return _cipher .encrypt (value .encode ()).decode ()

    def process_result_value (self ,value ,dialect ):
        if value is None :
            return None
        return _cipher .decrypt (value .encode ()).decode ()
