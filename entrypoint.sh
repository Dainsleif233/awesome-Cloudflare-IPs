#!/bin/sh
set -e

python fetch.py
python update.py
python push.py
