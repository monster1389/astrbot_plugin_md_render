"""桥接层 —— 消息组件与产物之间唯一的翻译处。

插件的其余模块都不 import ``astrbot.api.message_components``：进方向把原链拆成
文本与过境组件，出方向把产物翻成组件。组件类型的知识因此只在这个文件里。
"""
from __future__ import annotations

from typing import Any

from astrbot.api.message_components import File as AstrFile
from astrbot.api.message_components import Image, Plain

from render.artifacts import Artifact, Picture, SourceFile, Text


def split_chain(chain: list[Any]) -> tuple[str, list[Any]]:
    """把原始消息链拆成待解析文本与过境组件。

    Args:
        chain: AstrBot 原始消息链组件列表。

    Returns:
        (各 Plain 文本以换行拼接的结果, 非 Plain 组件列表)。过境组件保持原顺序，
        由调用方随首条消息原样发出。
    """
    text = "\n".join(c.text or "" for c in chain if isinstance(c, Plain))
    extras = [c for c in chain if not isinstance(c, Plain)]
    return text, extras


def to_components(artifacts: list[Artifact]) -> list[Any]:
    """把产物翻译为 AstrBot 消息组件。

    Args:
        artifacts: 产物列表。

    Returns:
        与产物顺序一致的消息组件列表。
    """
    return [_component(artifact) for artifact in artifacts]


def _component(artifact: Artifact) -> Any:
    """翻译单个产物。

    Args:
        artifact: 产物。

    Returns:
        对应的消息组件。

    Raises:
        TypeError: 产物类型未登记。
    """
    if isinstance(artifact, Text):
        return Plain(text=artifact.text)
    if isinstance(artifact, Picture):
        if artifact.path is None:
            return Image.fromBytes(artifact.png)
        return Image.fromFileSystem(artifact.path)
    if isinstance(artifact, SourceFile):
        return AstrFile(name=artifact.name, file=artifact.path)
    raise TypeError(f"未知的产物类型：{type(artifact).__name__}")
