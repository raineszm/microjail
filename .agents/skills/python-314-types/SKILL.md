---
name: python-314-types
description: Python 3.14 type annotation resolution rules. Use when unsure how type annotations are evaluated, whether to use TYPE_CHECKING, when from __future__ import annotations matters, or when ruff flags TC001/TC002/TC003.
---

# Python 3.14 Type Annotations

This project targets `requires-python = ">=3.14"` and `target-version = "py314"`.

## Core rule

Python 3.14 evaluates annotations **eagerly** by default. There is no PEP 563 deferred evaluation.

**NEVER add `from __future__ import annotations`.** It is a no-op in 3.14 (`__future__` imports for already-default features raise no error, but they are dead code and misleading).

## TYPE_CHECKING blocks

All type-only imports and definitions MUST go inside `if TYPE_CHECKING:`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from some_module import SomeType
    type JSON = dict[str, "JSON"] | list["JSON"]
```

### Names used only in annotations

Names referenced only in annotation position do NOT need to be in the module namespace at definition time. They only resolve when a type checker runs.

This is safe:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from heavy_library import ExpensiveType

def process(data: "ExpensiveType") -> None:  # stringified forward ref also fine
    ...
```

### ruff TC002 / TC003

ruff rules `TC002` (move third-party type-only imports into TYPE_CHECKING) and `TC003` (move stdlib type-only imports into TYPE_CHECKING) are **correct** for Python 3.14. They are not false positives.

### Import style

Prefer `if TYPE_CHECKING:` for type-only imports. Avoid `from __future__ import annotations` as a workaround — there is no workaround needed, and pattern is misleading in 3.14 code.

## The @dataclass exception

`@dataclass` accesses `__annotations__` at class **definition** time to build `__init__`. Field annotations must resolve to real objects at runtime.

```python
# WRONG — dataclass needs annotations at runtime
if TYPE_CHECKING:
    from some_module import SomeType

@dataclass
class Config:
    backend: SomeType  # NameError at class definition time
```

```python
# RIGHT — import at runtime
from some_module import SomeType

@dataclass
class Config:
    backend: SomeType
```

This applies to `msgspec.Struct`, `dataclasses.dataclass`, and any other decorator or base class that reads `__annotations__` at class-definition time.

## Quick reference

| Situation | Action |
|---|---|
| Type-only import needed | `if TYPE_CHECKING:` block |
| `from __future__ import annotations` | Never add; remove if found |
| ruff TC002/TC003 flags an import | Move it into `TYPE_CHECKING` |
| `@dataclass` field annotation | Import at runtime, not in `TYPE_CHECKING` |
| Annotation references name not imported at runtime | Fine — type checker resolves it |
