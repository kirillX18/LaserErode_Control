"""Крупные переиспользуемые панели-блоки, собранные из компонентов."""

from .device_card import DeviceCard
from .status_blocks import AlarmPanel, EventLogPanel, DiagnosticsPanel
from .control_blocks import QuickActionBar, ParameterForm, TestHarnessPanel
from .master_status import MasterStatusBar

__all__ = [
    "DeviceCard", "AlarmPanel", "EventLogPanel", "DiagnosticsPanel",
    "QuickActionBar", "ParameterForm", "TestHarnessPanel", "MasterStatusBar",
]
