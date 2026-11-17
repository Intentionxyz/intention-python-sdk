# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

InvalidReasonT = TypeVar("InvalidReasonT")


class ParsingError(Exception, Generic[InvalidReasonT]):
    invalid_reason: InvalidReasonT

    def __init__(self, message: str, invalid_reason: InvalidReasonT):
        super().__init__(message)
        self.invalid_reason = invalid_reason


@dataclass(frozen=True)
class ParsingResult(Generic[InvalidReasonT]):
    valid: bool
    invalid_reason: Optional[InvalidReasonT] = None
    invalid_reason_message: Optional[str] = None
