"""Installed only on dev.sh test PYTHONPATH: refuse external network in Python tests."""
import socket


def offline_connect(*args, **kwargs):
    raise OSError("dev.sh test: network disabled; use mocks for API calls")


socket.socket.connect = offline_connect
socket.socket.connect_ex = offline_connect
socket.create_connection = offline_connect
