"""产物 —— 流水线出口的唯一数据形态。

管线只认三种产物：纯文本、图片、源文件。AstrBot 的消息组件由
``render.bridge`` 在边缘翻译，本模块与 bridge 之外无人 import 组件类型。
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Text:
    """一段纯文本产物。

    Attributes:
        text: 待发文本，可含 markdown 原文。
    """
    text: str


@dataclass(frozen=True)
class Picture:
    """一张图片产物。

    Attributes:
        png: 已量化的 PNG 字节；``temp_ttl=0`` 时桥接层直接以字节发送。
        path: 落盘路径；None 表示不落盘。
    """
    png: bytes
    path: str | None = None


@dataclass(frozen=True)
class SourceFile:
    """一个源文件产物（.md）。

    Attributes:
        path: 落盘路径；文件名由它派生。
    """
    path: str

    @property
    def name(self) -> str:
        """文件名。

        Returns:
            路径的末段。
        """
        return os.path.basename(self.path)


Artifact = Text | Picture | SourceFile


@dataclass(frozen=True)
class Message:
    """流水线产出的一条待发送消息。

    Attributes:
        artifacts: 该条消息的产物列表，顺序即展示顺序。
        is_tail: 是否末条——末条不由 deliver 发送，留作 result.chain。
    """
    artifacts: list[Artifact]
    is_tail: bool


def has_media(artifacts: Iterable[Artifact]) -> bool:
    """判断产物列表是否含媒体（图片或源文件）。

    Args:
        artifacts: 产物列表。

    Returns:
        True 表示含媒体产物。
    """
    return any(not isinstance(a, Text) for a in artifacts)


def temp_paths(artifacts: Iterable[Artifact]) -> list[str]:
    """收集产物中落盘的临时文件路径（按出现顺序去重）。

    Args:
        artifacts: 产物列表。

    Returns:
        临时文件路径列表；不落盘的产物不产生路径。
    """
    paths = [
        a.path
        for a in artifacts
        if isinstance(a, (Picture, SourceFile)) and a.path
    ]
    return list(dict.fromkeys(paths))
