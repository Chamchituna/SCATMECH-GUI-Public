import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QScrollArea, QSizePolicy, QPushButton,
    QButtonGroup
)

from brdf_form import BRDFForm
from mie_form import MieForm
from reflect_form import ReflectForm
from rcw_form import RCWForm


class SCATMECHGui(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SCATMECH GUI")

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        def make_btn(text):
            button = QPushButton(text, self)
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            return button

        self.btn_brdf = make_btn("BRDF")
        self.btn_rcw = make_btn("RCW")
        self.btn_reflect = make_btn("Reflect")
        self.btn_mie = make_btn("Mie")

        buttons = [self.btn_brdf, self.btn_rcw, self.btn_reflect, self.btn_mie]
        for index, button in enumerate(buttons):
            self.btn_group.addButton(button, index)
            top.addWidget(button)
            top.setStretch(index, 1)

        root.addLayout(top)

        self.stack = QStackedWidget(self)

        self.brdf_form = BRDFForm()
        self.reflect_form = ReflectForm()
        self.mie_form = MieForm()
        self.rcw_form = RCWForm()

        def wrap_in_scroll(widget):
            scroll_area = QScrollArea(self)
            scroll_area.setWidgetResizable(True)
            scroll_area.setWidget(widget)
            scroll_area.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            return scroll_area

        self.stack.addWidget(wrap_in_scroll(self.brdf_form))
        self.stack.addWidget(wrap_in_scroll(self.rcw_form))
        self.stack.addWidget(wrap_in_scroll(self.reflect_form))
        self.stack.addWidget(wrap_in_scroll(self.mie_form))

        root.addWidget(self.stack, 1)

        def set_page(index):
            self.stack.setCurrentIndex(index)
            button = self.btn_group.button(index)
            if button and not button.isChecked():
                button.setChecked(True)

        self.btn_brdf.clicked.connect(lambda: set_page(0))
        self.btn_rcw.clicked.connect(lambda: set_page(1))
        self.btn_reflect.clicked.connect(lambda: set_page(2))
        self.btn_mie.clicked.connect(lambda: set_page(3))

        set_page(0)
        self.btn_brdf.setChecked(True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = SCATMECHGui()
    gui.show()
    sys.exit(app.exec_())
