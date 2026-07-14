import importlib.util
import os
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The layer sits on PYTHONPATH at runtime.
sys.path.insert(0, str(ROOT / "src" / "layers" / "common" / "python"))

# The tests only exercise pure logic, but the modules import boto3 at module
# load. Stub it out when it isn't installed so tests run anywhere.
try:
    import boto3  # noqa: F401
except ImportError:
    class _StubClientOrResource:
        def __getattr__(self, name):
            raise RuntimeError(f"AWS call attempted in unit test: {name}")

    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = lambda *_a, **_k: _StubClientOrResource()
    boto3_stub.resource = lambda *_a, **_k: _StubClientOrResource()
    sys.modules["boto3"] = boto3_stub

os.environ.setdefault("RUNS_TABLE", "test-runs")
os.environ.setdefault("CONFIG_BUCKET", "test-config")
os.environ.setdefault("LAKE_BUCKET", "test-lake")
os.environ.setdefault("ALERT_TOPIC_ARN", "arn:aws:sns:us-east-1:000000000000:test")
os.environ.setdefault("STATE_MACHINE_ARN", "arn:aws:states:us-east-1:000000000000:stateMachine:test")
os.environ.setdefault("ATHENA_DATABASE", "test")
os.environ.setdefault("ATHENA_WORKGROUP", "test")


def load_handler(function_name: str):
    """Import src/lambdas/<function_name>/handler.py under a unique name.

    Every Lambda ships a module called ``handler``; loading them by path
    avoids the name collision in one test process.
    """
    module_name = f"{function_name}_handler"
    if module_name in sys.modules:
        return sys.modules[module_name]
    path = ROOT / "src" / "lambdas" / function_name / "handler.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
