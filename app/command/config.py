import argparse
import json
from typing import Any
from ..config import load_config


def dataclass_to_dict(obj: Any) -> dict[str, Any]:
    if not hasattr(obj, "__dataclass_fields__"):
        raise ValueError("Object is not a dataclass instance")

    result = {}
    for field in obj.__dataclass_fields__.values():
        value = getattr(obj, field.name)
        if hasattr(value, "__dataclass_fields__"):
            result[field.name] = dataclass_to_dict(value)
        else:
            result[field.name] = value

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Show the current configuration.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the configuration.")
    args = parser.parse_args()

    config = dataclass_to_dict(load_config())
    if args.pretty:
        print(json.dumps(config, indent=2))
    else:
        print(config)


if __name__ == "__main__":
    main()
