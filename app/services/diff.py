from typing import Any


def diff_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    keys = set(before) | set(after)

    for key in keys:
        old_value = before.get(key)
        new_value = after.get(key)
        if old_value == new_value:
            continue
        if isinstance(old_value, dict) and isinstance(new_value, dict):
            nested = diff_reports(old_value, new_value)
            if nested:
                changes[key] = nested
        else:
            changes[key] = {"before": old_value, "after": new_value}

    return changes
