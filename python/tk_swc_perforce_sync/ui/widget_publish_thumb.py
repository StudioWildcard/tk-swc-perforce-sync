# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'widget_publish_thumb.ui'
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

class Ui_PublishThumbWidget(object):
    def setupUi(self, PublishThumbWidget):
        PublishThumbWidget.setObjectName("PublishThumbWidget")
        PublishThumbWidget.resize(1226, 782)
        self.verticalLayout_2 = QVBoxLayout(PublishThumbWidget)
        self.verticalLayout_2.setSpacing(1)
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.box = QFrame(PublishThumbWidget)
        self.box.setFrameShape(QFrame.StyledPanel)
        self.box.setFrameShadow(QFrame.Raised)
        self.box.setObjectName("box")
        self.verticalLayout = QVBoxLayout(self.box)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setContentsMargins(3, 3, 3, 3)
        self.verticalLayout.setObjectName("verticalLayout")
        self.thumbnail = QLabel(self.box)
        self.thumbnail.setText("")
        self.thumbnail.setPixmap(QPixmap(":/res/loading_512x400.png"))
        self.thumbnail.setScaledContents(True)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setObjectName("thumbnail")
        self.verticalLayout.addWidget(self.thumbnail)
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setSpacing(4)
        self.horizontalLayout.setContentsMargins(2, -1, 2, 2)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.label = QLabel(self.box)
        self.label.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignTop)
        self.label.setObjectName("label")
        self.horizontalLayout.addWidget(self.label)
        self.button = QToolButton(self.box)
        self.button.setMinimumSize(QSize(50, 0))
        self.button.setPopupMode(QToolButton.InstantPopup)
        self.button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.button.setObjectName("button")
        self.horizontalLayout.addWidget(self.button)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.verticalLayout_2.addWidget(self.box)

        self.retranslateUi(PublishThumbWidget)
        QMetaObject.connectSlotsByName(PublishThumbWidget)

    def retranslateUi(self, PublishThumbWidget):
        PublishThumbWidget.setWindowTitle(QApplication.translate("PublishThumbWidget", "Form", None))
        self.label.setText(QApplication.translate("PublishThumbWidget", "TextLabel\n"
"Foo", None))
        self.button.setText(QApplication.translate("PublishThumbWidget", "Actions", None))

from . import resources_rc
