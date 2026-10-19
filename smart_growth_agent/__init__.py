"""Registry-first local content application."""
import os

__version__ = "0.1.0"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
