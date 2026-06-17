"""Мелкие переиспользуемые виджеты, общие для всего интерфейса."""

from .buttons import (
    PrimaryButton, DangerButton, SmallButton, RedButton, GrayButton, StopButton,
)
from .labels import SectionTitle, ValueLabel
from .step_block import StepRow, StepControl
from .tabbar import AnimatedTabBar
from .status import (
    StatusDot, StatusBadge, MetricRow, MeterBar, IndicatorRow,
    LastMessageBar,
)
from .viewer3d import MeshViewer
from .position_view import PositionView

__all__ = [
    "PrimaryButton", "DangerButton", "SmallButton", "RedButton", "GrayButton",
    "StopButton",
    "SectionTitle", "ValueLabel", "StepRow", "StepControl", "AnimatedTabBar",
    "StatusDot", "StatusBadge", "MetricRow", "MeterBar", "IndicatorRow",
    "LastMessageBar", "MeshViewer", "PositionView",
]


def make_mesh_viewer(parent=None):
    """Фабрика 3D-вьюпорта: аппаратный OpenGL, если доступен PyOpenGL,
    иначе программный QPainter-рендер (работает без зависимостей)."""
    try:
        import OpenGL  # noqa: F401 — проверка наличия PyOpenGL
        from .viewer_gl import GLMeshViewer
        return GLMeshViewer(parent)
    except Exception:
        return MeshViewer(parent)
