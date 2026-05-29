# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'open_publish_form.ui'
#
#      by: pyside-uic 0.2.15 running on PySide 1.2.2
#
# WARNING! All changes made in this file will be lost!

from sgtk.platform.qt import QtCore
for name, cls in QtCore.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

from sgtk.platform.qt import QtGui
for name, cls in QtGui.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

class Ui_OpenPublishForm(object):
    def setupUi(self, OpenPublishForm):
        OpenPublishForm.setObjectName("OpenPublishForm")
        OpenPublishForm.resize(1228, 818)
        self.verticalLayout = QVBoxLayout(OpenPublishForm)
        self.verticalLayout.setSpacing(4)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout.setObjectName("verticalLayout")
        self.loader_form = QWidget(OpenPublishForm)
        self.loader_form.setStyleSheet("#loader_form {\n"
"background-color: rgb(255, 128, 0);\n"
"}")
        self.loader_form.setObjectName("loader_form")
        self.verticalLayout.addWidget(self.loader_form)
        self.break_line = QFrame(OpenPublishForm)
        self.break_line.setFrameShape(QFrame.HLine)
        self.break_line.setFrameShadow(QFrame.Sunken)
        self.break_line.setObjectName("break_line")
        self.verticalLayout.addWidget(self.break_line)
        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setContentsMargins(12, 8, 12, 12)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        spacerItem = QSpacerItem(0, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout_3.addItem(spacerItem)
        self.cancel_btn = QPushButton(OpenPublishForm)
        self.cancel_btn.setMinimumSize(QSize(90, 0))
        self.cancel_btn.setObjectName("cancel_btn")
        self.horizontalLayout_3.addWidget(self.cancel_btn)
        self.open_btn = QPushButton(OpenPublishForm)
        self.open_btn.setMinimumSize(QSize(90, 0))
        self.open_btn.setDefault(True)
        self.open_btn.setObjectName("open_btn")
        self.horizontalLayout_3.addWidget(self.open_btn)
        self.verticalLayout.addLayout(self.horizontalLayout_3)
        self.verticalLayout.setStretch(0, 1)

        self.retranslateUi(OpenPublishForm)
        QMetaObject.connectSlotsByName(OpenPublishForm)

    def retranslateUi(self, OpenPublishForm):
        OpenPublishForm.setWindowTitle(QApplication.translate("OpenPublishForm", "Form", None))
        self.cancel_btn.setText(QApplication.translate("OpenPublishForm", "Cancel", None))
        self.open_btn.setText(QApplication.translate("OpenPublishForm", "Open", None))

