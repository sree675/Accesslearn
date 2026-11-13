import os

import requests
import streamlit as st

try:
    API_URL = os.getenv("API_URL") or st.secrets["API_URL"]
except (KeyError, FileNotFoundError):
    API_URL = "http://127.0.0.1:8000"


class ApiError(Exception):
    pass


def call(method, path, **kwargs):
    headers = {}
    token = st.session_state.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.request(method, API_URL + path, headers=headers, timeout=60, **kwargs)
    except requests.RequestException:
        raise ApiError(f"Cannot reach the server at {API_URL}. Start the backend, then reload this page.")
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        if resp.status_code == 401 and token:
            st.session_state.pop("token", None)
            st.session_state.pop("user", None)
        raise ApiError(str(detail))
    return resp.json()


def get(path, **params):
    return call("GET", path, params={k: v for k, v in params.items() if v not in (None, "")})


def post(path, body=None):
    return call("POST", path, json=body if body is not None else {})


def put(path, body):
    return call("PUT", path, json=body)


def delete(path):
    return call("DELETE", path)
