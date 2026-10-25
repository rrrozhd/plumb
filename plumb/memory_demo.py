"""Compatibility launcher; implementation lives in plumb.interfaces.memory_demo."""
if __name__ == "__main__":
    from runpy import run_module

    run_module("plumb.interfaces.memory_demo", run_name="__main__")
