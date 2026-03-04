import os
import asyncio
from functools import wraps
from typing import Callable

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    OTEL_INSTALLED = True
except ImportError:
    OTEL_INSTALLED = False

def init_tracer(service_name: str = "AgentOS"):
    """
    初始化 OpenTelemetry Tracer。
    預設使用 Console Exporter，若需對接 Jaeger/Zipkin 可擴充此處。
    """
    if not OTEL_INSTALLED or os.getenv("ENABLE_OPENTELEMETRY", "false").lower() != "true":
        return None

    provider = TracerProvider()
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)

_tracer = init_tracer()

def trace_span(name: str = None):
    """
    Decorator for wrapping functions with OpenTelemetry Spans.
    Records inputs and execution time automatically.
    """
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                if not _tracer:
                    return await func(*args, **kwargs)
                span_name = name or func.__name__
                with _tracer.start_as_current_span(span_name) as span:
                    span.set_attribute("kwargs_keys", str(list(kwargs.keys())))
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        span.record_exception(e)
                        raise
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                if not _tracer:
                    return func(*args, **kwargs)
                span_name = name or func.__name__
                with _tracer.start_as_current_span(span_name) as span:
                    span.set_attribute("kwargs_keys", str(list(kwargs.keys())))
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        span.record_exception(e)
                        raise
            return sync_wrapper
    return decorator
