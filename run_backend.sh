#!/usr/bin/env bash
cd "$(dirname "$0")"
uvicorn backend.app.main:app --reload --port 8000
