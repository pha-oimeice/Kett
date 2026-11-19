from functools import partial

import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token


def verify_credential(credential: str, client_id: str) -> dict:
    with requests.Session() as session:
        return id_token.verify_oauth2_token(
            credential, partial(Request(session), timeout=5), audience=client_id
        )
