---
name: python-314-types
description: Python 3.14 type annotation resolution rules. Use when unsure how type annotations are evaluated, whether to use TYPE_CHECKING, when from __future__ import annotations matters, or when ruff flags TC001/TC002/TC003.
---

# Python 3.14 Type Annotations

This project targets `requires-python = ">=3.14"` and `target-version = "py314"`.

## Core rule

Python 3.14 evaluates annotations **lazily** by default (PEP 649 / PEP 749). Annotation expressions are not evaluated when the annotated code is created; they are saved and evaluated later when `__annotations__` is accessed.

## `from __future__ import annotations`

**Do not add it for new Python 3.14-only code.**

In Python 3.14, `from __future__ import annotations` is **not a no-op**. It switches to the older PEP 563 behavior where annotations are stored as **strings** (`f.__annotations__` → `{'param': 'annotation'}`).

```python
# Python 3.14+ — preferred (lazy evaluation, no future import)
def f(x: SomeLaterType) -> None:
    ...
```

```python
# PEP 563 mode — annotations stored as strings
from __future__ import annotations

def f(x: SomeLaterType) -> None:
    ...
# f.__annotations__ == {'x': 'SomeLaterType', 'return': 'None'}
```

Add the future import only when you specifically need stringized annotations for compatibility with older tooling or code that expects strings. The import is planned for deprecation/removal, though not before Python 3.13 reaches end of life.

Note: the import name is `annotations`, not `annotatoins`; the misspelled version would fail.

## TYPE_CHECKING blocks

Because annotations are lazy, names used only in annotation position do not need to be in the module namespace at function-definition time. They resolve later when `__annotations__` is first accessed.

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from some_module import SomeType
    type JSON = dict[str, "JSON"] | list["JSON"]

def process(data: SomeType) -> None:  # no NameError at definition time
    ...
```

### When TYPE_CHECKING works

For **regular functions and methods** (non-dataclass, non-Struct) where `__annotations__` is never accessed at runtime, names imported only in `TYPE_CHECKING` are fine. The type checker resolves them; Python never looks.

### When TYPE_CHECKING breaks

Any code that accesses `__annotations__` at runtime will try to resolve the lazy annotations. If the names were only imported inside `TYPE_CHECKING`, they won't be in the module namespace → **NameError**.

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from some_module import SomeType

def f(x: SomeType) -> None:
    ...
# f.__annotations__  # NameError: SomeType not defined
```

## ruff TC002 / TC003

`TC002` (move third-party type-only imports into TYPE_CHECKING) and `TC003` (move stdlib type-only imports into TYPE_CHECKING) are **correct** when the annotated object is a regular function whose `__annotations__` is never introspected at runtime.

They are **false positives** when:

- The annotation is on a `@dataclass` or `msgspec.Struct` field (see below)
- Code accesses `__annotations__` or calls `typing.get_type_hints()` on the annotated object

In practice: treat TC002/TC003 as correct for `def`-level annotations and wrong for class-field annotations. When in doubt, keep the import at module level — the overhead is minimal and the safety is real.

## The `@dataclass` / `msgspec.Struct` exception

`@dataclass` and `msgspec.Struct` access `__annotations__` at class **definition** time to build `__init__`. Python's lazy evaluation triggers immediately — field annotations must resolve to real objects at runtime.

```python
# WRONG — dataclass triggers __annotations__ → NameError
if TYPE_CHECKING:
    from some_module import SomeType

@dataclass
class Config:
    backend: SomeType
```

```python
# RIGHT — import at module level
from some_module import SomeType

@dataclass
class Config:
    backend: SomeType
```

This applies to `msgspec.Struct`, `dataclasses.dataclass`, `typing.NamedTuple`, and any other decorator or base class that reads `__annotations__` at class-definition time. For classes that do not read `__annotations__` (plain `class`, non-dataclass), TYPE_CHECKING imports are fine.

## Quick reference

| Situation | Action |
|---|---|
| New Python 3.14-only code | No `from __future__ import annotations` |
| Type-only import for a regular `def` | `if TYPE_CHECKING:` block |
| Type-only import for a `@dataclass` / `Struct` field | Import at module level |
| `from __future__ import annotations` in 3.14 | Valid but switches to PEP 563 strings; avoid for new code |
| ruff TC002/TC003 on a field annotation | False positive — keep at module level |
| ruff TC002/TC003 on a `def` annotation | Move into `TYPE_CHECKING` |
| `get_type_hints()` is called on a function | Names in annotations must be at module level |
