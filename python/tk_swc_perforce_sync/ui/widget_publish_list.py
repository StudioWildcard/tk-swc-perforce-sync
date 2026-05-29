# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'widget_publish_list.ui'
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

class Ui_PublishListWidget(object):
    def setupUi(self, PublishListWidget):
        PublishListWidget.setObjectName("PublishListWidget")
        PublishListWidget.resize(1226, 782)
        self.horizontalLayout_3 = QHBoxLayout(PublishListWidget)
        self.horizontalLayout_3.setSpacing(1)
        self.horizontalLayout_3.setContentsMargins(1, 1, 1, 1)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.box = QFrame(PublishListWidget)
        self.box.setFrameShape(QFrame.StyledPanel)
        self.box.setFrameShadow(QFrame.Raised)
        self.box.setObjectName("box")
        self.horizontalLayout = QHBoxLayout(self.box)
        self.horizontalLayout.setSpacing(10)
        self.horizontalLayout.setContentsMargins(10, 2, 10, 2)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.thumbnail = QLabel(self.box)
        self.thumbnail.setMinimumSize(QSize(50, 40))
        self.thumbnail.setMaximumSize(QSize(50, 40))
        self.thumbnail.setText("")
        self.thumbnail.setScaledContents(True)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setObjectName("thumbnail")
        self.horizontalLayout.addWidget(self.thumbnail)
        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setSpacing(2)
        self.verticalLayout.setObjectName("verticalLayout")
        spacerItem = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.label_1 = QLabel(self.box)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_1.sizePolicy().hasHeightForWidth())
        self.label_1.setSizePolicy(sizePolicy)
        self.label_1.setStyleSheet("font-size: 11px")
        self.label_1.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignVCenter)
        self.label_1.setWordWrap(True)
        self.label_1.setObjectName("label_1")
        self.verticalLayout.addWidget(self.label_1)
        self.label_2 = QLabel(self.box)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.label_2.sizePolicy().hasHeightForWidth())
        self.label_2.setSizePolicy(sizePolicy)
        self.label_2.setStyleSheet("font-size: 10px")
        self.label_2.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignVCenter)
        self.label_2.setWordWrap(True)
        self.label_2.setObjectName("label_2")
        self.verticalLayout.addWidget(self.label_2)
        spacerItem1 = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem1)
        self.horizontalLayout.addLayout(self.verticalLayout)
        self.button = QToolButton(self.box)
        self.button.setMinimumSize(QSize(50, 0))
        self.button.setPopupMode(QToolButton.InstantPopup)
        self.button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.button.setObjectName("button")
        self.horizontalLayout.addWidget(self.button)
        self.horizontalLayout_3.addWidget(self.box)

        self.retranslateUi(PublishListWidget)
        QMetaObject.connectSlotsByName(PublishListWidget)

    def retranslateUi(self, PublishListWidget):
        PublishListWidget.setWindowTitle(QApplication.translate("PublishListWidget", "Form", None))
        self.label_1.setText(QApplication.translate("PublishListWidget", "Rendered image ABX123", None))
        self.label_2.setText(QApplication.translate("PublishListWidget", "v014 by John Smith on 2000-01-01 12:23", None))
        self.button.setText(QApplication.translate("PublishListWidget", "Actions", None))

from . import resources_rc
