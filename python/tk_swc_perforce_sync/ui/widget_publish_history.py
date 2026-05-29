# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'widget_publish_history.ui'
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

class Ui_PublishHistoryWidget(object):
    def setupUi(self, PublishHistoryWidget):
        PublishHistoryWidget.setObjectName("PublishHistoryWidget")
        PublishHistoryWidget.resize(1226, 782)
        self.horizontalLayout_3 = QHBoxLayout(PublishHistoryWidget)
        self.horizontalLayout_3.setSpacing(1)
        self.horizontalLayout_3.setContentsMargins(1, 1, 1, 1)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.box = QFrame(PublishHistoryWidget)
        self.box.setFrameShape(QFrame.StyledPanel)
        self.box.setFrameShadow(QFrame.Raised)
        self.box.setObjectName("box")
        self.horizontalLayout_2 = QHBoxLayout(self.box)
        self.horizontalLayout_2.setSpacing(4)
        self.horizontalLayout_2.setContentsMargins(1, 2, 1, 2)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.thumbnail = QLabel(self.box)
        self.thumbnail.setMinimumSize(QSize(75, 75))
        self.thumbnail.setMaximumSize(QSize(75, 75))
        self.thumbnail.setText("")
        self.thumbnail.setScaledContents(True)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setObjectName("thumbnail")
        self.horizontalLayout_2.addWidget(self.thumbnail)
        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.header_label = QLabel(self.box)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.header_label.sizePolicy().hasHeightForWidth())
        self.header_label.setSizePolicy(sizePolicy)
        self.header_label.setObjectName("header_label")
        self.horizontalLayout.addWidget(self.header_label)
        self.button = QToolButton(self.box)
        self.button.setMinimumSize(QSize(50, 0))
        self.button.setPopupMode(QToolButton.InstantPopup)
        self.button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.button.setObjectName("button")
        self.horizontalLayout.addWidget(self.button)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.body_label = QLabel(self.box)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.body_label.sizePolicy().hasHeightForWidth())
        self.body_label.setSizePolicy(sizePolicy)
        self.body_label.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignTop)
        self.body_label.setWordWrap(True)
        self.body_label.setObjectName("body_label")
        self.verticalLayout.addWidget(self.body_label)
        self.horizontalLayout_2.addLayout(self.verticalLayout)
        self.horizontalLayout_3.addWidget(self.box)

        self.retranslateUi(PublishHistoryWidget)
        QMetaObject.connectSlotsByName(PublishHistoryWidget)

    def retranslateUi(self, PublishHistoryWidget):
        PublishHistoryWidget.setWindowTitle(QApplication.translate("PublishHistoryWidget", "Form", None))
        self.header_label.setText(QApplication.translate("PublishHistoryWidget", "Header", None))
        self.button.setText(QApplication.translate("PublishHistoryWidget", "Actions", None))
        self.body_label.setText(QApplication.translate("PublishHistoryWidget", "TextLabel\n"
"Foo\n"
"Bar", None))

from . import resources_rc
