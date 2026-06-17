"""TOML profile 读取与 dataclass 校验。

本模块负责把配置文件中的命名 section 安全转换为强类型 dataclass 实例。它只接受
显式 section/table，不允许未知 key、错误类型或 `profile_name` 重复声明，也不会
读取任何密钥或发起网络请求。
"""

from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

import tomllib

from memory_benchmark.core import ConfigurationError


ConfigT = TypeVar("ConfigT")


def load_typed_profile(
    path: str | Path,
    profile_name: str,
    config_type: type[ConfigT],
) -> ConfigT:
    """从 TOML section 读取并构造强类型 profile。

    输入:
        path: TOML 配置文件路径。
        profile_name: 需要读取的 section 名称。
        config_type: 目标 dataclass 类型。

    输出:
        ConfigT: 通过校验后的 dataclass 实例。

    异常:
        ConfigurationError: 文件缺失、格式错误、section 不存在、未知 key、
            字段类型不匹配或 dataclass 初始化失败。
    """

    resolved_path = Path(path).expanduser().resolve()
    if not resolved_path.is_file():
        raise ConfigurationError(f"Profile TOML file missing: {resolved_path}")

    payload = _load_toml_document(resolved_path)
    normalized_profile_name = profile_name.strip()
    if not normalized_profile_name:
        raise ConfigurationError("Profile name is required")

    _ensure_top_level_sections(payload, resolved_path)

    section = payload.get(normalized_profile_name)
    if section is None:
        raise ConfigurationError(
            f"Missing profile section '{normalized_profile_name}' in {resolved_path}"
        )
    if not isinstance(section, dict):
        raise ConfigurationError(
            f"Profile section '{normalized_profile_name}' must be a TOML table: {resolved_path}"
        )
    if not is_dataclass(config_type):
        raise ConfigurationError(f"Profile target must be a dataclass: {config_type!r}")

    config_fields = {field.name: field for field in fields(config_type) if field.init}
    type_hints = get_type_hints(config_type)

    if "profile_name" in section and "profile_name" in config_fields:
        raise ConfigurationError(
            f"Profile '{normalized_profile_name}' in {resolved_path} must not declare profile_name"
        )

    unknown_keys = sorted(key for key in section if key not in config_fields)
    if unknown_keys:
        raise ConfigurationError(
            f"Unknown key(s) in profile '{normalized_profile_name}' at {resolved_path}: "
            f"{', '.join(unknown_keys)}"
        )

    kwargs: dict[str, Any] = {}
    for field_name, field in config_fields.items():
        if field_name == "profile_name":
            kwargs[field_name] = normalized_profile_name
            continue

        if field_name not in section:
            continue

        raw_value = section[field_name]
        expected_type = type_hints.get(field_name, field.type)
        kwargs[field_name] = _normalize_profile_value(
            raw_value=raw_value,
            expected_type=expected_type,
            field_name=field_name,
            profile_name=normalized_profile_name,
            source_path=resolved_path,
        )

    missing_fields = [
        field_name
        for field_name, field in config_fields.items()
        if field_name not in kwargs
        and field.default is MISSING
        and field.default_factory is MISSING
    ]
    if missing_fields:
        raise ConfigurationError(
            f"Missing required key(s) in profile '{normalized_profile_name}' at {resolved_path}: "
            f"{', '.join(sorted(missing_fields))}"
        )

    try:
        return config_type(**kwargs)
    except ConfigurationError:
        raise
    except TypeError as exc:
        raise ConfigurationError(
            f"Invalid profile '{normalized_profile_name}' in {resolved_path}: {exc}"
        ) from None


def _load_toml_document(path: Path) -> dict[str, Any]:
    """读取 TOML 文档并包装解析错误。

    输入:
        path: TOML 文件路径。

    输出:
        dict[str, Any]: 解析后的 TOML 文档。
    """

    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML profile file: {path}") from None


def _ensure_top_level_sections(payload: dict[str, Any], source_path: Path) -> None:
    """确保 TOML 顶层只包含 section/table。

    输入:
        payload: 解析后的 TOML 文档。
        source_path: 原始文件路径。

    异常:
        ConfigurationError: 顶层出现标量、列表或其他非 table 结构。
    """

    non_table_keys = sorted(key for key, value in payload.items() if not isinstance(value, dict))
    if non_table_keys:
        raise ConfigurationError(
            f"TOML profile top level must contain only sections: {source_path}"
        )


def _normalize_profile_value(
    raw_value: Any,
    expected_type: Any,
    field_name: str,
    profile_name: str,
    source_path: Path,
) -> Any:
    """校验并规范化单个 profile 字段值。

    输入:
        raw_value: TOML 中的原始字段值。
        expected_type: dataclass 字段的目标类型注解。
        field_name: 字段名。
        profile_name: 当前 section 名称。
        source_path: 原始文件路径。

    输出:
        Any: 通过类型检查后的值，必要时会做轻量转换。

    异常:
        ConfigurationError: 类型不匹配。
    """

    if _value_matches_type(raw_value, expected_type):
        return _coerce_profile_value(raw_value, expected_type)

    expected_description = _describe_expected_type(expected_type)
    actual_description = type(raw_value).__name__
    raise ConfigurationError(
        f"Profile '{profile_name}' field '{field_name}' in {source_path} has invalid type: "
        f"expected {expected_description}, got {actual_description}"
    )


def _coerce_profile_value(value: Any, expected_type: Any) -> Any:
    """将 TOML 解析值转换为 dataclass 需要的运行时类型。

    输入:
        value: 已通过类型检查的字段值。
        expected_type: dataclass 字段类型注解。

    输出:
        Any: 运行时值。
    """

    origin = get_origin(expected_type)
    if origin is None:
        if expected_type is Path and not isinstance(value, Path):
            return Path(value)
        if expected_type is float and isinstance(value, int) and not isinstance(value, bool):
            return float(value)
        return value

    if origin is tuple and isinstance(value, tuple):
        args = get_args(expected_type)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_coerce_profile_value(item, args[0]) for item in value)
        return tuple(
            _coerce_profile_value(item, item_type)
            for item, item_type in zip(value, args, strict=False)
        )

    if origin is list and isinstance(value, list):
        item_types = get_args(expected_type) or (Any,)
        item_type = item_types[0]
        return [_coerce_profile_value(item, item_type) for item in value]

    if origin is set and isinstance(value, set):
        item_types = get_args(expected_type) or (Any,)
        item_type = item_types[0]
        return {_coerce_profile_value(item, item_type) for item in value}

    if origin is frozenset and isinstance(value, frozenset):
        item_types = get_args(expected_type) or (Any,)
        item_type = item_types[0]
        return frozenset(_coerce_profile_value(item, item_type) for item in value)

    return value


def _value_matches_type(value: Any, expected_type: Any) -> bool:
    """判断 TOML 值是否符合 dataclass 字段类型。

    输入:
        value: TOML 解析值。
        expected_type: dataclass 字段类型注解。

    输出:
        bool: 值符合类型时返回 True。
    """

    origin = get_origin(expected_type)
    if expected_type is Any:
        return True
    if origin is None:
        if expected_type is Path:
            return isinstance(value, (str, Path))
        if expected_type is str:
            return isinstance(value, str)
        if expected_type is bool:
            return isinstance(value, bool)
        if expected_type is int:
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type is float:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if isinstance(expected_type, type):
            return isinstance(value, expected_type)
        return True

    if origin is list:
        return isinstance(value, list) and _iterable_matches_type(value, get_args(expected_type))
    if origin is tuple:
        return isinstance(value, tuple) and _iterable_matches_type(value, get_args(expected_type))
    if origin is set:
        return isinstance(value, set) and _iterable_matches_type(value, get_args(expected_type))
    if origin is frozenset:
        return isinstance(value, frozenset) and _iterable_matches_type(value, get_args(expected_type))
    if origin is dict:
        return isinstance(value, dict)
    if origin is type(None):
        return value is None

    union_args = get_args(expected_type)
    if union_args:
        return any(_value_matches_type(value, arg) for arg in union_args)
    return True


def _iterable_matches_type(value: Any, type_args: tuple[Any, ...]) -> bool:
    """校验列表、元组和集合的元素类型。

    输入:
        value: 待检查的可迭代值。
        type_args: 元素类型参数。

    输出:
        bool: 元素类型全部匹配时返回 True。
    """

    if not type_args:
        return True
    if len(type_args) == 2 and type_args[1] is Ellipsis:
        return all(_value_matches_type(item, type_args[0]) for item in value)
    if len(type_args) == 1:
        return all(_value_matches_type(item, type_args[0]) for item in value)
    if len(type_args) != len(value):
        return False
    return all(
        _value_matches_type(item, item_type)
        for item, item_type in zip(value, type_args, strict=False)
    )


def _describe_expected_type(expected_type: Any) -> str:
    """生成类型错误消息中的可读描述。"""

    origin = get_origin(expected_type)
    if expected_type is Any:
        return "any"
    if origin is None:
        if isinstance(expected_type, type):
            return expected_type.__name__
        return str(expected_type)

    args = get_args(expected_type)
    if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
        return f"tuple[{_describe_expected_type(args[0])}, ...]"
    if not args:
        return getattr(origin, "__name__", str(origin))
    joined = ", ".join(_describe_expected_type(arg) for arg in args)
    origin_name = getattr(origin, "__name__", str(origin))
    return f"{origin_name}[{joined}]"
