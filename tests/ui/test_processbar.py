import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from pyleem_gui.ui.processbar import ProcessBar


def test_process_click_selects_ancestor_tab(qtbot):
    from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    page0 = QWidget()
    tabs.addTab(page0, "A")
    page1 = QWidget()
    nested = QWidget()
    QVBoxLayout(page1).addWidget(nested)
    tabs.addTab(page1, "B")

    bar = ProcessBar()
    bar.set_tab_widget(tabs)
    tabs.setCurrentIndex(0)

    bar._on_click(nested)
    assert tabs.currentWidget() is page1
