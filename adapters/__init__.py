"""Adapters connect the tax engine to outside systems.

Each adapter converts the system's order into an engine call and writes the
result back. The engine in taxengine/ never imports anything from here.
"""
